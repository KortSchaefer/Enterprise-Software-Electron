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

    def delete(self):
        self._operation = "delete"
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
        if self._operation == "delete":
            deleted = [deepcopy(row) for row in rows if all(row.get(column) == value for column, value in self._filters)]
            self.client.data[self.table_name] = [row for row in rows if not all(row.get(column) == value for column, value in self._filters)]
            return FakeResult(deleted)
        raise AssertionError("Unsupported table operation")


class FakeSupabase:
    def __init__(self):
        self._id_counters = {
            "users": 4,
            "tenant_memberships": 4,
            "app_sessions": 1,
            "inventory_items": 1,
            "messages": 5,
            "pos_menu_categories": 5,
            "pos_menu_items": 9,
            "pos_tables": 4,
            "pos_tickets": 4,
            "pos_ticket_items": 20,
            "pos_ticket_prints": 3,
            "audit_logs": 1,
        }
        self.data = {
            "users": [
                {"id": 1, "tenant_id": "demo-tenant", "email": "alice@demo-tenant.local", "password_hash": hash_password("Password123!")},
                {"id": 2, "tenant_id": "demo-tenant", "email": "bob@demo-tenant.local", "password_hash": hash_password("Password123!")},
                {"id": 3, "tenant_id": "other-tenant", "email": "mallory@other-tenant.local", "password_hash": hash_password("Password123!")},
            ],
            "tenant_memberships": [
                {"id": 1, "tenant_id": "demo-tenant", "user_id": 1, "role": "manager", "is_active": 1},
                {"id": 2, "tenant_id": "demo-tenant", "user_id": 2, "role": "staff", "is_active": 1},
                {"id": 3, "tenant_id": "other-tenant", "user_id": 3, "role": "staff", "is_active": 1},
            ],
            "app_sessions": [],
            "tenant_apps": [],
            "audit_logs": [],
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
            "messages": [
                {
                    "id": 1,
                    "tenant_id": "demo-tenant",
                    "from_user_id": 2,
                    "to_user_id": 1,
                    "text": "Need help with the stock count?",
                    "created_at": "2026-04-20T08:00:00+00:00",
                    "read_at": None,
                },
                {
                    "id": 2,
                    "tenant_id": "demo-tenant",
                    "from_user_id": 1,
                    "to_user_id": 2,
                    "text": "I am reviewing it now.",
                    "created_at": "2026-04-20T08:05:00+00:00",
                    "read_at": None,
                },
                {
                    "id": 3,
                    "tenant_id": "demo-tenant",
                    "from_user_id": 2,
                    "to_user_id": 1,
                    "text": "There is one pallet left to verify.",
                    "created_at": "2026-04-20T08:10:00+00:00",
                    "read_at": None,
                },
                {
                    "id": 4,
                    "tenant_id": "other-tenant",
                    "from_user_id": 3,
                    "to_user_id": 3,
                    "text": "Other tenant traffic",
                    "created_at": "2026-04-20T09:00:00+00:00",
                    "read_at": None,
                },
            ],
            "pos_menu_categories": [
                {"id": 1, "tenant_id": "demo-tenant", "name": "Steaks", "sort_order": 10},
                {"id": 2, "tenant_id": "demo-tenant", "name": "Drinks", "sort_order": 20},
            ],
            "pos_menu_items": [
                {"id": 1, "tenant_id": "demo-tenant", "category_id": 1, "name": "8 oz Sirloin", "description": "", "price_cents": 2299, "is_active": 1, "sort_order": 10},
                {"id": 2, "tenant_id": "demo-tenant", "category_id": 1, "name": "12 oz Ribeye", "description": "", "price_cents": 3199, "is_active": 1, "sort_order": 20},
                {"id": 3, "tenant_id": "demo-tenant", "category_id": 2, "name": "Water", "description": "", "price_cents": 299, "is_active": 1, "sort_order": 10},
            ],
            "pos_tables": [
                {"id": 1, "tenant_id": "demo-tenant", "table_number": "122", "guest_count": 6, "status": "firing", "opened_at": "2026-04-20T14:15:00+00:00", "updated_at": "2026-04-20T14:39:00+00:00", "closed_at": None, "assigned_to_user_id": 1},
                {"id": 2, "tenant_id": "demo-tenant", "table_number": "111", "guest_count": 2, "status": "ready", "opened_at": "2026-04-20T13:40:00+00:00", "updated_at": "2026-04-20T14:22:00+00:00", "closed_at": None, "assigned_to_user_id": 1},
                {"id": 3, "tenant_id": "other-tenant", "table_number": "7", "guest_count": 1, "status": "open", "opened_at": "2026-04-20T14:00:00+00:00", "updated_at": "2026-04-20T14:05:00+00:00", "closed_at": None, "assigned_to_user_id": 3},
            ],
            "pos_tickets": [
                {"id": 1, "tenant_id": "demo-tenant", "table_id": 1, "status": "firing", "subtotal_cents": 7395, "printed_at": "2026-04-20T14:34:00+00:00", "kitchen_note": "", "created_at": "2026-04-20T14:15:00+00:00", "updated_at": "2026-04-20T14:39:00+00:00"},
                {"id": 2, "tenant_id": "demo-tenant", "table_id": 2, "status": "ready", "subtotal_cents": 4897, "printed_at": "2026-04-20T14:18:00+00:00", "kitchen_note": "", "created_at": "2026-04-20T13:40:00+00:00", "updated_at": "2026-04-20T14:22:00+00:00"},
                {"id": 3, "tenant_id": "other-tenant", "table_id": 3, "status": "open", "subtotal_cents": 299, "printed_at": None, "kitchen_note": "", "created_at": "2026-04-20T14:00:00+00:00", "updated_at": "2026-04-20T14:05:00+00:00"},
            ],
            "pos_ticket_items": [
                {"id": 1, "tenant_id": "demo-tenant", "ticket_id": 1, "menu_item_id": 1, "item_name_snapshot": "8 oz Sirloin", "unit_price_cents": 2299, "quantity": 1, "line_total_cents": 2299, "course": None, "seat_label": None, "created_at": "2026-04-20T14:16:00+00:00", "updated_at": "2026-04-20T14:16:00+00:00"},
                {"id": 2, "tenant_id": "demo-tenant", "ticket_id": 1, "menu_item_id": 2, "item_name_snapshot": "12 oz Ribeye", "unit_price_cents": 3199, "quantity": 1, "line_total_cents": 3199, "course": None, "seat_label": None, "created_at": "2026-04-20T14:17:00+00:00", "updated_at": "2026-04-20T14:17:00+00:00"},
                {"id": 3, "tenant_id": "demo-tenant", "ticket_id": 1, "menu_item_id": 3, "item_name_snapshot": "Water", "unit_price_cents": 299, "quantity": 4, "line_total_cents": 1196, "course": None, "seat_label": None, "created_at": "2026-04-20T14:18:00+00:00", "updated_at": "2026-04-20T14:18:00+00:00"},
                {"id": 4, "tenant_id": "demo-tenant", "ticket_id": 2, "menu_item_id": 1, "item_name_snapshot": "8 oz Sirloin", "unit_price_cents": 2299, "quantity": 2, "line_total_cents": 4598, "course": None, "seat_label": None, "created_at": "2026-04-20T13:45:00+00:00", "updated_at": "2026-04-20T13:45:00+00:00"},
                {"id": 5, "tenant_id": "demo-tenant", "ticket_id": 2, "menu_item_id": 3, "item_name_snapshot": "Water", "unit_price_cents": 299, "quantity": 1, "line_total_cents": 299, "course": None, "seat_label": None, "created_at": "2026-04-20T13:46:00+00:00", "updated_at": "2026-04-20T13:46:00+00:00"},
                {"id": 6, "tenant_id": "other-tenant", "ticket_id": 3, "menu_item_id": 3, "item_name_snapshot": "Water", "unit_price_cents": 299, "quantity": 1, "line_total_cents": 299, "course": None, "seat_label": None, "created_at": "2026-04-20T14:00:00+00:00", "updated_at": "2026-04-20T14:00:00+00:00"},
            ],
            "pos_ticket_prints": [
                {"id": 1, "tenant_id": "demo-tenant", "ticket_id": 1, "printed_by": "alice@demo-tenant.local", "printed_at": "2026-04-20T14:34:00+00:00", "print_type": "guest_check"},
                {"id": 2, "tenant_id": "demo-tenant", "ticket_id": 2, "printed_by": "alice@demo-tenant.local", "printed_at": "2026-04-20T14:18:00+00:00", "print_type": "guest_check"},
            ],
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
            patch("app.pos.get_supabase", return_value=self.fake_supabase),
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

    def test_chat_conversation_summary_returns_unread_and_preview(self):
        headers = self._login_headers()
        response = self.client.get("/chat/conversations", headers=headers)
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(len(payload), 1)
        conversation = payload[0]
        self.assertEqual(conversation["other_user_id"], 2)
        self.assertEqual(conversation["unread_count"], 2)
        self.assertEqual(conversation["last_message_text"], "There is one pallet left to verify.")
        self.assertEqual(conversation["last_message_direction"], "incoming")

    def test_chat_thread_paginates_and_marks_read(self):
        headers = self._login_headers()
        response = self.client.get("/chat/conversations/2/messages?limit=2", headers=headers)
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(len(payload["messages"]), 2)
        self.assertTrue(payload["has_more"])
        self.assertEqual(payload["messages"][0]["id"], 2)
        self.assertEqual(payload["messages"][1]["id"], 3)

        older = self.client.get(
            f"/chat/conversations/2/messages?limit=2&before={payload['next_before']}",
            headers=headers,
        )
        self.assertEqual(older.status_code, 200)
        older_payload = older.json()
        self.assertEqual(len(older_payload["messages"]), 1)
        self.assertEqual(older_payload["messages"][0]["id"], 1)

        read_response = self.client.post("/chat/conversations/2/read", headers=headers)
        self.assertEqual(read_response.status_code, 200)
        unread_after = [row for row in self.fake_supabase.data["messages"] if row["tenant_id"] == "demo-tenant" and row["to_user_id"] == 1 and row["from_user_id"] == 2]
        self.assertTrue(all(row["read_at"] for row in unread_after))

    def test_chat_tenant_isolation_for_other_user(self):
        headers = self._login_headers()
        response = self.client.get("/chat/conversations/3/messages", headers=headers)
        self.assertEqual(response.status_code, 404)

    def test_pos_board_returns_only_authenticated_tenant(self):
        headers = self._login_headers()
        response = self.client.get("/pos/board", headers=headers)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 2)
        self.assertEqual({row["table_number"] for row in payload}, {"111", "122"})
        self.assertTrue(all(row["tenant_id"] == "demo-tenant" for row in payload))

    def test_pos_create_table_creates_ticket(self):
        headers = self._login_headers()
        response = self.client.post("/pos/tables", headers=headers, json={"table_number": "130", "guest_count": 4})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["table"]["table_number"], "130")
        self.assertTrue(any(row["table_id"] == payload["table"]["id"] for row in self.fake_supabase.data["pos_tickets"]))

    def test_pos_item_mutations_recalculate_subtotal(self):
        headers = self._login_headers()
        add_response = self.client.post("/pos/tables/2/items", headers=headers, json={"menu_item_id": 3, "quantity": 2})
        self.assertEqual(add_response.status_code, 200)
        self.assertEqual(add_response.json()["table"]["subtotal_cents"], 5495)

        new_item = max((row for row in self.fake_supabase.data["pos_ticket_items"] if row["ticket_id"] == 2), key=lambda row: row["id"])
        update_response = self.client.patch(f"/pos/tables/2/items/{new_item['id']}", headers=headers, json={"quantity": 3})
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["table"]["subtotal_cents"], 5794)

        delete_response = self.client.delete(f"/pos/tables/2/items/{new_item['id']}", headers=headers)
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["table"]["subtotal_cents"], 4897)

    def test_pos_print_and_close_record_state(self):
        headers = self._login_headers()
        print_response = self.client.post("/pos/tables/1/print", headers=headers, json={"print_type": "guest_check"})
        self.assertEqual(print_response.status_code, 200)
        self.assertEqual(len(self.fake_supabase.data["pos_ticket_prints"]), 3)

        close_response = self.client.post("/pos/tables/1/close", headers=headers, json={})
        self.assertEqual(close_response.status_code, 200)
        self.assertEqual(close_response.json()["table"]["status"], "closed")
        table_row = next(row for row in self.fake_supabase.data["pos_tables"] if row["id"] == 1)
        self.assertEqual(table_row["status"], "closed")

    def test_pos_staff_access_is_forbidden(self):
        response = self.client.post(
            "/auth/login",
            json={"tenant_id": "demo-tenant", "email": "bob@demo-tenant.local", "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 200)
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        board_response = self.client.get("/pos/board", headers=headers)
        self.assertEqual(board_response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
