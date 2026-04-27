import pytest
from fastapi.testclient import TestClient
from app.main import app

pytestmark = pytest.mark.real_auth

TEST_TENANT_ID = "demo-tenant"
TEST_EMAIL = "admin@demo-tenant.local"
TEST_PASSWORD = "Password123!"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers(client: TestClient) -> dict[str, str]:
    login_response = client.post(
        "/auth/login",
        json={
            "tenant_id": TEST_TENANT_ID,
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        },
    )
    assert login_response.status_code == 200, login_response.text
    body = login_response.json()

    token = body.get("access_token")
    assert token, f"No access_token in login response: {body}"

    assert body["tenant_id"] == TEST_TENANT_ID, body
    assert body["email"] == TEST_EMAIL, body

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def recipient_user_id(client: TestClient, auth_headers: dict[str, str]) -> int:
    response = client.get("/users", headers=auth_headers)
    assert response.status_code == 200, response.text
    users = response.json()
    session_response = client.get("/auth/session", headers=auth_headers)
    assert session_response.status_code == 200, session_response.text
    current_user_id = session_response.json()["user_id"]
    for user in users:
        if user["id"] != current_user_id:
            return user["id"]
    raise AssertionError("Expected at least one chat recipient in the demo tenant")


def test_chat_send_success(client: TestClient, auth_headers: dict[str, str], recipient_user_id: int):
    response = client.post(
        "/chat/messages",
        json={
            "to_user_id": recipient_user_id,
            "text": "Hello!",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["to_user_id"] == recipient_user_id
    assert body["text"] == "Hello!"


def test_chat_send_requires_text(client: TestClient, auth_headers: dict[str, str], recipient_user_id: int):
    response = client.post(
        "/chat/messages",
        json={
            "to_user_id": recipient_user_id,
            "text": "",
        },
        headers=auth_headers,
    )

    assert response.status_code in (400, 422), response.text


def test_chat_send_requires_recipient(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/chat/messages",
        json={
            "text": "Hello!",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422, response.text


def test_chat_send_requires_valid_recipient(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/chat/messages",
        json={
            "to_user_id": 0,
            "text": "Hello!",
        },
        headers=auth_headers,
    )

    assert response.status_code in (400, 404, 422), response.text


def test_chat_messages_success(client: TestClient, auth_headers: dict[str, str], recipient_user_id: int):
    send_response = client.post(
        "/chat/messages",
        json={
            "to_user_id": recipient_user_id,
            "text": "First message",
        },
        headers=auth_headers,
    )
    assert send_response.status_code == 200, send_response.text

    response = client.get(
        f"/chat/conversations/{recipient_user_id}/messages",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["messages"], list)
    assert len(body["messages"]) >= 1


def test_chat_messages_requires_valid_with_user_id(client: TestClient, auth_headers: dict[str, str]):
    response = client.get(
        "/chat/conversations/0/messages",
        headers=auth_headers,
    )

    assert response.status_code in (400, 404, 422), response.text


def test_chat_messages_returns_list_shape(client: TestClient, auth_headers: dict[str, str], recipient_user_id: int):
    response = client.get(
        f"/chat/conversations/{recipient_user_id}/messages",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["messages"], list)
