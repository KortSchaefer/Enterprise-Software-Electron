from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException


ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

DEFAULT_TIMEOUT = float(os.getenv("SUPABASE_TIMEOUT_SECONDS", "30"))
READ_RETRIES = int(os.getenv("SUPABASE_READ_RETRIES", "2"))


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _format_filter_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class QueryResult:
    data: Any


@dataclass
class TableQuery:
    client: "SupabaseClient"
    table_name: str
    method: str = "GET"
    params: list[tuple[str, str]] = field(default_factory=list)
    payload: Any = None
    prefer_headers: list[str] = field(default_factory=list)

    def select(self, columns: str = "*") -> "TableQuery":
        self.method = "GET"
        self.params = [(key, value) for key, value in self.params if key != "select"]
        self.params.append(("select", columns))
        return self

    def eq(self, column: str, value: Any) -> "TableQuery":
        self.params.append((column, f"eq.{_format_filter_value(value)}"))
        return self

    def gte(self, column: str, value: Any) -> "TableQuery":
        self.params.append((column, f"gte.{_format_filter_value(value)}"))
        return self

    def lte(self, column: str, value: Any) -> "TableQuery":
        self.params.append((column, f"lte.{_format_filter_value(value)}"))
        return self

    def order(self, column: str, desc: bool = False) -> "TableQuery":
        direction = "desc" if desc else "asc"
        self.params = [(key, value) for key, value in self.params if key != "order"]
        self.params.append(("order", f"{column}.{direction}"))
        return self

    def limit(self, count: int) -> "TableQuery":
        self.params = [(key, value) for key, value in self.params if key != "limit"]
        self.params.append(("limit", str(count)))
        return self

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> "TableQuery":
        self.method = "POST"
        self.payload = payload
        self.prefer_headers = ["return=representation"]
        return self

    def update(self, payload: dict[str, Any]) -> "TableQuery":
        self.method = "PATCH"
        self.payload = payload
        self.prefer_headers = ["return=representation"]
        return self

    def delete(self) -> "TableQuery":
        self.method = "DELETE"
        self.prefer_headers = ["return=representation"]
        return self

    def execute(self, bearer_token: str | None = None) -> QueryResult:
        return self.client.execute(self, bearer_token=bearer_token)


class SupabaseClient:
    def __init__(self, url: str, key: str):
        self.base_url = f"{url.rstrip('/')}/rest/v1"
        self.key = key

    def table(self, table_name: str) -> TableQuery:
        return TableQuery(client=self, table_name=table_name)

    def rpc(self, function_name: str, payload: dict[str, Any], bearer_token: str | None = None) -> QueryResult:
        return self._request(
            method="POST",
            path=f"/rpc/{function_name}",
            params=[],
            payload=payload,
            prefer_headers=["return=representation"],
            bearer_token=bearer_token,
        )

    def execute(self, query: TableQuery, bearer_token: str | None = None) -> QueryResult:
        return self._request(
            method=query.method,
            path=f"/{query.table_name}",
            params=query.params,
            payload=query.payload,
            prefer_headers=query.prefer_headers,
            bearer_token=bearer_token,
        )

    def _request(
        self,
        method: str,
        path: str,
        params: list[tuple[str, str]],
        payload: Any,
        prefer_headers: list[str],
        bearer_token: str | None,
    ) -> QueryResult:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {bearer_token or self.key}",
        }
        if method in {"POST", "PATCH"}:
            headers["Content-Type"] = "application/json"
        if prefer_headers:
            headers["Prefer"] = ",".join(prefer_headers)

        attempts = READ_RETRIES + 1 if method == "GET" else 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                response = httpx.request(
                    method=method,
                    url=f"{self.base_url}{path}",
                    headers=headers,
                    params=params,
                    json=payload,
                    timeout=DEFAULT_TIMEOUT,
                )
                if response.status_code >= 400:
                    raise self._map_http_error(response)

                if not response.content:
                    return QueryResult(data=[])

                data = response.json()
                return QueryResult(data=data)
            except httpx.HTTPError as error:
                last_error = error
                if method != "GET" or attempt == attempts - 1:
                    raise HTTPException(status_code=503, detail="Database request failed.") from error
                time.sleep(0.2 * (attempt + 1))

        raise HTTPException(status_code=503, detail="Database request failed.") from last_error

    def _map_http_error(self, response: httpx.Response) -> HTTPException:
        detail = "Supabase request failed."
        payload: dict[str, Any] | None = None
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = payload.get("message") or payload.get("detail") or response.text.strip() or detail
            else:
                detail = response.text.strip() or detail
        except ValueError:
            detail = response.text.strip() or detail

        code = payload.get("code") if isinstance(payload, dict) else None
        if response.status_code in {401, 403}:
            return HTTPException(status_code=response.status_code, detail="Unauthorized database access.")
        if response.status_code == 404 or code == "PGRST205":
            return HTTPException(status_code=404, detail=detail)
        if response.status_code == 409 or code in {"23505", "23503", "23514"}:
            mapped_detail = detail
            if code == "23505":
                mapped_detail = "Conflict with existing data."
            elif code == "23503":
                mapped_detail = "Referenced data was not found."
            elif code == "23514":
                mapped_detail = "Request violates a database constraint."
            return HTTPException(status_code=409 if code == "23505" else 400, detail=mapped_detail)
        return HTTPException(status_code=500, detail=detail)


@lru_cache
def get_supabase() -> SupabaseClient:
    url = _require_env("SUPABASE_URL")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_KEY", "").strip()
        or _require_env("SUPABASE_ANON_KEY")
    )
    return SupabaseClient(url, key)


def rows(result: Any) -> list[dict[str, Any]]:
    data = getattr(result, "data", None) or []
    return list(data)


def first_row(result: Any) -> dict[str, Any] | None:
    data = rows(result)
    return data[0] if data else None


def require_row(row: dict[str, Any] | None, status_code: int, detail: str) -> dict[str, Any]:
    if row is None:
        raise HTTPException(status_code=status_code, detail=detail)
    return row
