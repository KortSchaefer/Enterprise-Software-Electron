import uuid

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.auth import SessionContext, get_session_context
from app.database import get_supabase


TEST_TENANT_ID = f"tenant-test-{uuid.uuid4().hex[:8]}"


def _best_effort_delete_tenant_rows(table: str, column: str = "tenant_id") -> None:
    supabase = get_supabase()
    try:
        supabase.table(table).delete().eq(column, TEST_TENANT_ID).execute()
    except HTTPException as error:
        # Teardown should not fail tests because of transient Supabase connectivity.
        if error.status_code not in {404, 503}:
            raise


def _purge_test_tenant_data() -> None:
    # child -> parent delete order
    for table in (
        "messages",
        "inventory_movements",
        "inventory_items",
        "tenant_apps",
        "app_sessions",
        "tenant_memberships",
        "users",
        "manager_alerts",
        "timesheet_approvals",
        "time_events",
        "shifts",
        "audit_logs",
        "employees",
        "time_policies",
    ):
        _best_effort_delete_tenant_rows(table)
    _best_effort_delete_tenant_rows("tenants", column="id")


def _ensure_test_tenant() -> None:
    supabase = get_supabase()
    tenant = (
        supabase.table("tenants")
        .select("id")
        .eq("id", TEST_TENANT_ID)
        .limit(1)
        .execute()
    )
    if getattr(tenant, "data", None):
        return
    try:
        supabase.table("tenants").insert(
            {
                "id": TEST_TENANT_ID,
                "name": "Pytest Tenant",
                "is_active": 1,
            }
        ).execute()
    except HTTPException as error:
        # Ignore duplicate key if another test worker/process created it.
        if error.status_code != 409:
            raise


@pytest.fixture(autouse=True)
def override_auth(request):
    # real_auth tests use real login/session and should not be overridden
    if request.node.get_closest_marker("real_auth"):
        yield
        return

    _purge_test_tenant_data()
    _ensure_test_tenant()

    def fake_get_session_context():
        return SessionContext(
            session_id=1,
            session_token="test-token",
            user_id=1,
            email="admin@example.com",
            tenant_id=TEST_TENANT_ID,
            role="admin",
        )

    app.dependency_overrides[get_session_context] = fake_get_session_context
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        _purge_test_tenant_data()


@pytest.fixture()
def client():
    return TestClient(app)