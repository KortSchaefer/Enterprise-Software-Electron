from uuid import uuid4

from fastapi.testclient import TestClient


def _sku(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}".upper()


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_activation_validate_ok(client: TestClient):
    tenant_key = "a" * 64
    response = client.post("/activation/validate", json={"tenant_key": tenant_key})
    assert response.status_code == 200

    data = response.json()
    assert data["tenant_id"] == "tenant-aaaaaaaaaaaa"
    assert data["business_name"] == "Business AAAAAAAAAAAA"
    assert data["api_base_url"] == "https://api.example.com/tenant-aaaaaaaaaaaa"


def test_activation_validate_bad_key(client: TestClient):
    response = client.post("/activation/validate", json={"tenant_key": "123"})
    assert response.status_code == 422


def test_app_catalog(client: TestClient):
    response = client.get("/apps/catalog")
    assert response.status_code == 200

    data = response.json()
    assert any(entry["key"] == "inventory" for entry in data)
    assert any(entry["key"] == "timeclock" for entry in data)
    assert any(entry["key"] == "chat" for entry in data)


def test_install_timeclock_app(client: TestClient):
    response = client.post("/apps/install", json={"app_key": "timeclock"})
    assert response.status_code == 200

    data = response.json()
    assert data["app_key"] == "timeclock"
    assert "installed_at" in data


def test_install_unknown_app_returns_404(client: TestClient):
    response = client.post("/apps/install", json={"app_key": "does-not-exist"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown app key."


def test_list_installed_apps(client: TestClient):
    install_response = client.post("/apps/install", json={"app_key": "inventory"})
    assert install_response.status_code == 200

    response = client.get("/apps/installed")
    assert response.status_code == 200

    data = response.json()
    assert any(row["app_key"] == "inventory" for row in data)


def test_create_inventory_item(client: TestClient):
    sku = _sku("abc")
    response = client.post(
        "/inventory/items",
        json={
            "sku": sku,
            "name": "Widget",
            "description": "Test item",
            "quantity_on_hand": 10,
            "reorder_point": 5,
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["sku"] == sku
    assert data["name"] == "Widget"
    assert data["description"] == "Test item"
    assert data["quantity_on_hand"] == 10
    assert data["reorder_point"] == 5


def test_create_inventory_item_validation_error(client: TestClient):
    response = client.post(
        "/inventory/items",
        json={
            "sku": "",
            "name": "",
            "description": "",
            "quantity_on_hand": -1,
            "reorder_point": -5,
        },
    )
    assert response.status_code == 422


def test_list_inventory_items(client: TestClient):
    sku = _sku("abc")
    create_response = client.post(
        "/inventory/items",
        json={
            "sku": sku,
            "name": "Gadget",
            "description": "",
            "quantity_on_hand": 3,
            "reorder_point": 5,
        },
    )
    assert create_response.status_code == 200

    response = client.get("/inventory/items")
    assert response.status_code == 200

    data = response.json()
    assert any(row["sku"] == sku for row in data)


def test_list_inventory_items_low_stock_only(client: TestClient):
    low_sku = _sku("low")
    healthy_sku = _sku("high")

    low_response = client.post(
        "/inventory/items",
        json={
            "sku": low_sku,
            "name": "Low Stock Item",
            "description": "",
            "quantity_on_hand": 2,
            "reorder_point": 5,
        },
    )
    assert low_response.status_code == 200

    healthy_response = client.post(
        "/inventory/items",
        json={
            "sku": healthy_sku,
            "name": "Healthy Stock Item",
            "description": "",
            "quantity_on_hand": 20,
            "reorder_point": 5,
        },
    )
    assert healthy_response.status_code == 200

    response = client.get("/inventory/items", params={"low_stock_only": "true"})
    assert response.status_code == 200

    data = response.json()
    assert any(row["sku"] == low_sku for row in data)
    assert not any(row["sku"] == healthy_sku for row in data)


def test_create_duplicate_inventory_item_returns_409(client: TestClient):
    sku = _sku("dup")

    first_response = client.post(
        "/inventory/items",
        json={
            "sku": sku,
            "name": "Duplicate Test",
            "description": "",
            "quantity_on_hand": 4,
            "reorder_point": 2,
        },
    )
    assert first_response.status_code == 200

    second_response = client.post(
        "/inventory/items",
        json={
            "sku": sku,
            "name": "Duplicate Test Again",
            "description": "",
            "quantity_on_hand": 10,
            "reorder_point": 3,
        },
    )
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "SKU already exists for this tenant."


def test_adjust_inventory_success(client: TestClient):
    sku = _sku("adj")
    create_response = client.post(
        "/inventory/items",
        json={
            "sku": sku,
            "name": "Adjustable Item",
            "description": "",
            "quantity_on_hand": 10,
            "reorder_point": 5,
        },
    )
    assert create_response.status_code == 200
    item = create_response.json()

    response = client.post(
        "/inventory/adjust",
        json={
            "item_id": item["id"],
            "change_amount": 5,
            "reason": "Restock",
            "performed_by": "admin@example.com",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == item["id"]
    assert data["quantity_on_hand"] == 15


def test_adjust_inventory_zero_change_returns_400(client: TestClient):
    sku = _sku("adj")
    create_response = client.post(
        "/inventory/items",
        json={
            "sku": sku,
            "name": "Zero Change Item",
            "description": "",
            "quantity_on_hand": 8,
            "reorder_point": 2,
        },
    )
    assert create_response.status_code == 200
    item = create_response.json()

    response = client.post(
        "/inventory/adjust",
        json={
            "item_id": item["id"],
            "change_amount": 0,
            "reason": "No-op",
            "performed_by": "admin@example.com",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "change_amount cannot be zero."