from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.security import hash_password


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self._filters = []
        self._payload = None
        self._operation = "select"

    def select(self, _columns="*"):
        self._operation = "select"
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def limit(self, _count):
        return self

    def order(self, _column, desc=False):
        return self

    def insert(self, payload):
        self._operation = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._operation = "update"
        self._payload = payload
        return self

    def execute(self, bearer_token=None):
        rows = self.client.data[self.table_name]
        matched = [row for row in rows if all(row.get(column) == value for column, value in self._filters)]
        if self._operation == "select":
            return FakeResult(deepcopy(matched))
        if self._operation == "insert":
            payload = deepcopy(self._payload)
            payload.setdefault("id", self.client.next_id(self.table_name))
            rows.append(payload)
            return FakeResult([deepcopy(payload)])
        if self._operation == "update":
            updated = []
            for row in rows:
                if all(row.get(column) == value for column, value in self._filters):
                    row.update(deepcopy(self._payload))
                    updated.append(deepcopy(row))
            return FakeResult(updated)
        raise AssertionError("Unsupported table operation")


class FakeSupabase:
    def __init__(self):
        self._id_counters = {"users": 3, "tenant_memberships": 3, "app_sessions": 1, "inventory_items": 1}
        self.data = {
            "users": [
                {"id": 1, "tenant_id": "demo-tenant", "email": "alice@demo-tenant.local", "password_hash": hash_password("Password123!")},
                {"id": 2, "tenant_id": "other-tenant", "email": "mallory@other-tenant.local", "password_hash": hash_password("Password123!")},
            ],
            "tenant_memberships": [
                {"id": 1, "tenant_id": "demo-tenant", "user_id": 1, "role": "manager", "is_active": 1},
                {"id": 2, "tenant_id": "other-tenant", "user_id": 2, "role": "staff", "is_active": 1},
            ],
            "app_sessions": [],
            "tenant_apps": [],
            "inventory_items": [
                {
                    "id": 1,
                    "tenant_id": "demo-tenant",
                    "sku": "SKU-1",
                    "name": "Widget",
                    "description": "",
                    "quantity_on_hand": 5,
                    "reorder_point": 1,
                }
            ],
            "inventory_movements": [],
        }

    def next_id(self, table_name):
        self._id_counters.setdefault(table_name, 1)
        value = self._id_counters[table_name]
        self._id_counters[table_name] += 1
        return value

    def table(self, table_name):
        self.data.setdefault(table_name, [])
        return FakeTable(self, table_name)

    def rpc(self, function_name, payload, bearer_token=None):
        if function_name != "adjust_inventory_item":
            raise AssertionError("Unexpected RPC function")
        row = next(
            (item for item in self.data["inventory_items"] if item["id"] == payload["p_item_id"] and item["tenant_id"] == payload["p_tenant_id"]),
            None,
        )
        if row is None:
            return FakeResult([])
        next_qty = row["quantity_on_hand"] + payload["p_change_amount"]
        if next_qty < 0:
            raise ValueError("Negative inventory not allowed")
        row["quantity_on_hand"] = next_qty
        self.data["inventory_movements"].append(
            {
                "id": self.next_id("inventory_movements"),
                "item_id": row["id"],
                "tenant_id": row["tenant_id"],
                "change_amount": payload["p_change_amount"],
                "reason": payload["p_reason"],
                "performed_by": payload["p_performed_by"],
            }
        )
        return FakeResult([deepcopy(row)])


class BackendAuthAndInventoryTests(unittest.TestCase):
    def setUp(self):
        self.fake_supabase = FakeSupabase()
        patchers = [
            patch("app.main.get_supabase", return_value=self.fake_supabase),
            patch("app.auth.get_supabase", return_value=self.fake_supabase),
            patch("app.chat.get_supabase", return_value=self.fake_supabase),
            patch("app.timeclock.get_supabase", return_value=self.fake_supabase),
        ]
        self._patchers = patchers
        for patcher in patchers:
            patcher.start()
        self.client = TestClient(app)

    def tearDown(self):
        for patcher in reversed(self._patchers):
            patcher.stop()

    def _login_headers(self):
        response = self.client.post(
            "/auth/login",
            json={"tenant_id": "demo-tenant", "email": "alice@demo-tenant.local", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 200)
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_login_creates_session_token(self):
        response = self.client.post(
            "/auth/login",
            json={"tenant_id": "demo-tenant", "email": "alice@demo-tenant.local", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["tenant_id"], "demo-tenant")
        self.assertEqual(payload["email"], "alice@demo-tenant.local")
        self.assertTrue(payload["access_token"])
        self.assertEqual(len(self.fake_supabase.data["app_sessions"]), 1)

    def test_protected_route_requires_bearer_token(self):
        response = self.client.get("/users")
        self.assertEqual(response.status_code, 401)

    def test_inventory_adjust_uses_authenticated_tenant(self):
        headers = self._login_headers()
        response = self.client.post(
            "/inventory/adjust",
            headers=headers,
            json={"item_id": 1, "change_amount": 3, "reason": "restock", "performed_by": "alice"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["tenant_id"], "demo-tenant")
        self.assertEqual(payload["quantity_on_hand"], 8)
        self.assertEqual(len(self.fake_supabase.data["inventory_movements"]), 1)


if __name__ == "__main__":
    unittest.main()
