import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth import SessionContext, get_session_context
from app.database import get_supabase


TEST_TENANT_ID = f"tenant-test-{uuid.uuid4().hex[:8]}"


def _purge_test_tenant_data() -> None:
    supabase = get_supabase()

    # child -> parent delete order
    for table in (
        "manager_alerts",
        "timesheet_approvals",
        "time_events",
        "shifts",
        "audit_logs",
        "employees",
        "time_policies",
    ):
        supabase.table(table).delete().eq("tenant_id", TEST_TENANT_ID).execute()


@pytest.fixture(autouse=True)
def override_auth(request):
    # real_auth tests use real login/session and should not be overridden
    if request.node.get_closest_marker("real_auth"):
        yield
        return

    _purge_test_tenant_data()

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