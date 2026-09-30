from typing import Any

import pytest
from fastapi.testclient import TestClient

URL = "/api/transactions"
PASSWORD = "correct-horse-battery"


def log_in_as(client: TestClient, email: str) -> None:
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).is_success


def trade(side: str, quantity: Any, day: int = 1, **overrides: Any) -> dict[str, Any]:
    body = {
        "symbol": "aapl",
        "asset_type": "stock",
        "side": side,
        "quantity": quantity,
        "price": "150.25",
        "fee": "1.5",
        "executed_at": f"2026-01-{day:02d}T15:00:00Z",
    }
    return body | overrides


@pytest.fixture
def alice(client: TestClient) -> TestClient:
    log_in_as(client, "alice@example.com")
    return client


def test_full_ledger_flow(client: TestClient) -> None:
    log_in_as(client, "alice@example.com")

    created = client.post(URL, json=trade("buy", "10", day=1))
    assert created.status_code == 201
    buy = created.json()
    assert buy["symbol"] == "AAPL"
    assert (buy["quantity"], buy["price"], buy["fee"], buy["currency"]) == (
        "10",
        "150.25",
        "1.5",
        "USD",
    )

    assert client.post(URL, json=trade("sell", "4", day=2)).status_code == 201

    oversell = client.post(URL, json=trade("sell", "6.0000000001", day=3))
    assert oversell.status_code == 400
    assert "only 6 held" in oversell.json()["detail"]

    # Another user's ledger is invisible, both in the list and by id.
    log_in_as(client, "bob@example.com")
    bob_trade = client.post(URL, json=trade("buy", "1", symbol="btc", asset_type="crypto"))
    assert [t["symbol"] for t in client.get(URL).json()] == ["BTC"]
    assert client.get(f"{URL}/{buy['id']}").status_code == 404
    assert client.delete(f"{URL}/{buy['id']}").status_code == 404

    log_in_as(client, "alice@example.com")
    listed = client.get(URL).json()
    assert [(t["side"], t["quantity"]) for t in listed] == [("sell", "4"), ("buy", "10")]
    assert bob_trade.json()["id"] not in {t["id"] for t in listed}

    # PATCH is validated as if applied: shrinking the buy below what was sold is rejected...
    too_small = client.patch(f"{URL}/{buy['id']}", json={"quantity": "3"})
    assert too_small.status_code == 400
    assert client.get(f"{URL}/{buy['id']}").json()["quantity"] == "10"
    # ...while shrinking it to exactly what was sold is fine.
    patched = client.patch(f"{URL}/{buy['id']}", json={"quantity": "4", "price": "99.99"})
    assert patched.status_code == 200
    assert (patched.json()["quantity"], patched.json()["price"]) == ("4", "99.99")

    assert client.delete(f"{URL}/{buy['id']}").status_code == 204
    assert client.get(f"{URL}/{buy['id']}").status_code == 404


def test_decimal_precision_survives_round_trip(alice: TestClient) -> None:
    for quantity in ("0.1", "0.2"):
        assert alice.post(URL, json=trade("buy", quantity, symbol="eth")).status_code == 201
    # Float arithmetic would make holdings 0.30000000000000004 or 0.29999999999999998.
    assert alice.post(URL, json=trade("sell", "0.3", day=2, symbol="eth")).status_code == 201

    tiny = alice.post(URL, json=trade("buy", "0.0000000001", price="0.0000123456", symbol="shib"))
    assert (tiny.json()["quantity"], tiny.json()["price"]) == ("0.0000000001", "0.0000123456")


def test_json_float_numbers_are_rejected(alice: TestClient) -> None:
    response = alice.post(URL, json=trade("buy", "1", price=150.25))
    assert response.status_code == 422
    assert "strings" in response.text


def test_json_integers_are_accepted(alice: TestClient) -> None:
    response = alice.post(URL, json=trade("buy", 3, price=100))
    assert response.status_code == 201
    assert response.json()["quantity"] == "3"


def test_sell_backdated_before_buy_is_rejected(alice: TestClient) -> None:
    alice.post(URL, json=trade("buy", "5", day=10))
    assert alice.post(URL, json=trade("sell", "5", day=5)).status_code == 400


def test_patch_moving_buy_after_its_sell_is_rejected(alice: TestClient) -> None:
    buy = alice.post(URL, json=trade("buy", "5", day=1)).json()
    alice.post(URL, json=trade("sell", "5", day=2))
    moved = alice.patch(f"{URL}/{buy['id']}", json={"executed_at": "2026-01-03T00:00:00Z"})
    assert moved.status_code == 400


def test_patch_changing_symbol_rechecks_old_symbol(alice: TestClient) -> None:
    buy = alice.post(URL, json=trade("buy", "5")).json()
    alice.post(URL, json=trade("sell", "2", day=2))
    # Moving the buy to MSFT would leave the AAPL sell uncovered.
    assert alice.patch(f"{URL}/{buy['id']}", json={"symbol": "msft"}).status_code == 400


def test_list_filters_by_symbol_case_insensitively(alice: TestClient) -> None:
    alice.post(URL, json=trade("buy", "1", symbol="aapl"))
    alice.post(URL, json=trade("buy", "1", symbol="msft"))
    assert [t["symbol"] for t in alice.get(URL, params={"symbol": "Msft"}).json()] == ["MSFT"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"quantity": "0"},
        {"quantity": "-1"},
        {"price": "0"},
        {"fee": "-0.01"},
        {"symbol": "   "},
        {"asset_type": "bond"},
        {"currency": "ILS"},
        {"quantity": "1.00000000001"},
        {"executed_at": "2026-01-01T15:00:00"},
    ],
)
def test_invalid_create_bodies_are_rejected(alice: TestClient, overrides: dict[str, Any]) -> None:
    assert alice.post(URL, json=trade("buy", "1") | overrides).status_code == 422


def test_patch_rejects_explicit_null(alice: TestClient) -> None:
    buy = alice.post(URL, json=trade("buy", "1")).json()
    assert alice.patch(f"{URL}/{buy['id']}", json={"quantity": None}).status_code == 422


def test_transactions_require_auth(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.post(URL, json=trade("buy", "1")).status_code == 401
