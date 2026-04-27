import pytest
from fastapi.testclient import TestClient
from app.main import app

pytestmark = pytest.mark.real_auth

TEST_TENANT_ID = "demo-tenant"
TEST_EMAIL = "dsandifer@live.com"
TEST_PASSWORD = "secret"
TEST_USER_ID = 4
TEST_RECIPIENT_USER_ID = 2


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

    assert body["user_id"] == TEST_USER_ID, body
    assert body["tenant_id"] == TEST_TENANT_ID, body
    assert body["email"] == TEST_EMAIL, body

    return {"Authorization": f"Bearer {token}"}


def test_chat_send_success(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/chat/send",
        json={
            "to_user_id": TEST_RECIPIENT_USER_ID,
            "text": "Hello!",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True


def test_chat_send_requires_text(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/chat/send",
        json={
            "to_user_id": TEST_RECIPIENT_USER_ID,
            "text": "",
        },
        headers=auth_headers,
    )

    assert response.status_code in (400, 422), response.text


def test_chat_send_requires_recipient(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/chat/send",
        json={
            "text": "Hello!",
        },
        headers=auth_headers,
    )

    assert response.status_code == 422, response.text


def test_chat_send_requires_valid_recipient(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/chat/send",
        json={
            "to_user_id": 0,
            "text": "Hello!",
        },
        headers=auth_headers,
    )

    assert response.status_code in (400, 404, 422), response.text


def test_chat_messages_success(client: TestClient, auth_headers: dict[str, str]):
    send_response = client.post(
        "/chat/send",
        json={
            "to_user_id": TEST_RECIPIENT_USER_ID,
            "text": "First message",
        },
        headers=auth_headers,
    )
    assert send_response.status_code == 200, send_response.text

    response = client.post(
        "/chat/messages",
        json={
            "with_user_id": TEST_RECIPIENT_USER_ID,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["messages"], list)
    assert len(body["messages"]) >= 1


def test_chat_messages_requires_with_user_id(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/chat/messages",
        json={},
        headers=auth_headers,
    )

    assert response.status_code == 422, response.text


def test_chat_messages_requires_valid_with_user_id(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/chat/messages",
        json={
            "with_user_id": 0,
        },
        headers=auth_headers,
    )

    assert response.status_code in (400, 404, 422), response.text


def test_chat_messages_returns_list_shape(client: TestClient, auth_headers: dict[str, str]):
    response = client.post(
        "/chat/messages",
        json={
            "with_user_id": TEST_RECIPIENT_USER_ID,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["messages"], list)