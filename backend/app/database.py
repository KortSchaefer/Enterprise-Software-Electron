from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException
from dotenv import load_dotenv


ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _format_filter_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


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

    def execute(self) -> QueryResult:
        return self.client.execute(self)


class SupabaseClient:
    def __init__(self, url: str, key: str):
        self.base_url = f"{url.rstrip('/')}/rest/v1"
        self.key = key

    def table(self, table_name: str) -> TableQuery:
        return TableQuery(client=self, table_name=table_name)

    def execute(self, query: TableQuery) -> QueryResult:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
        }
        if query.method in {"POST", "PATCH"}:
            headers["Content-Type"] = "application/json"
        if query.prefer_headers:
            headers["Prefer"] = ",".join(query.prefer_headers)

        response = httpx.request(
            method=query.method,
            url=f"{self.base_url}/{query.table_name}",
            headers=headers,
            params=query.params,
            json=query.payload,
            timeout=30.0,
        )
        if response.status_code >= 400:
            detail = response.text.strip() or "Supabase request failed."
            raise HTTPException(status_code=500, detail=detail)

        if not response.content:
            return QueryResult(data=[])

        data = response.json()
        return QueryResult(data=data)


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
