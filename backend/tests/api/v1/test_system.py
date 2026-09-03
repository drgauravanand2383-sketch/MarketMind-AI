"""Tests for `GET /api/v1/version`, `/configuration`, `/capabilities`, `/services`."""

from __future__ import annotations

from fastapi import status
from fastapi.testclient import TestClient

# --- /version -----------------------------------------------------------


def test_version_returns_expected_fields(client: TestClient) -> None:
    data = client.get("/api/v1/version").json()["data"]

    assert data["api_version"] == "v1"
    assert data["application_version"]
    assert data["environment"]


def test_version_missing_settings_returns_503(bare_client: TestClient) -> None:
    response = bare_client.get("/api/v1/version")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# --- /system/scheduler -----------------------------------------------------------


def test_scheduler_health_reports_a_running_dispatching_scheduler(client: TestClient) -> None:
    data = client.get("/api/v1/system/scheduler").json()["data"]

    assert data["scheduler_running"] is True
    # Freshly bootstrapped: the timer is alive (canary grace applies even
    # before its first tick) and the watchdog has never had to intervene.
    assert data["dispatching"] is True
    assert data["watchdog_recoveries"] == 0
    assert isinstance(data["registered_jobs"], int)
    assert "next_execution" in data and "last_canary" in data


def test_scheduler_health_missing_service_returns_503(bare_client: TestClient) -> None:
    response = bare_client.get("/api/v1/system/scheduler")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# --- /configuration -----------------------------------------------------------


def test_configuration_returns_expected_fields(client: TestClient) -> None:
    data = client.get("/api/v1/configuration").json()["data"]

    assert "environment" in data
    assert "log_level" in data
    assert "api_version_prefix" in data
    assert isinstance(data["allowed_origins"], list)
    assert isinstance(data["watchlist_max_size"], int)
    assert isinstance(data["scheduler_enabled"], bool)
    assert isinstance(data["rss_feed_count"], int)


def test_configuration_never_exposes_secrets(client: TestClient) -> None:
    body = client.get("/api/v1/configuration").json()
    serialized = str(body).lower()

    assert "password" not in serialized
    assert "api_key" not in serialized
    assert "secret" not in serialized
    assert "change-me" not in serialized


def test_configuration_api_version_prefix_matches_router_mount(client: TestClient) -> None:
    data = client.get("/api/v1/configuration").json()["data"]

    assert data["api_version_prefix"] == "/api/v1"


def test_configuration_missing_settings_returns_503(bare_client: TestClient) -> None:
    response = bare_client.get("/api/v1/configuration")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# --- /capabilities -----------------------------------------------------------


def test_capabilities_reports_every_wired_engine_as_available(client: TestClient) -> None:
    capabilities = client.get("/api/v1/capabilities").json()["data"]["capabilities"]

    for name in (
        "watchlist", "screening", "signal_detection", "alerts", "recommendations",
        "strategy_evaluation", "risk_analytics", "backtesting", "explainability",
    ):
        assert capabilities[name] is True, f"{name} expected available"


def test_capabilities_reports_unimplemented_features_as_unavailable(client: TestClient) -> None:
    capabilities = client.get("/api/v1/capabilities").json()["data"]["capabilities"]

    for name in ("broker_integration", "notifications", "authentication"):
        assert capabilities[name] is False


def test_capabilities_reports_live_market_data_false_under_default_mock_config(client: TestClient) -> None:
    """Milestone 13: unlike the three names above, `live_market_data` is
    no longer permanently hardcoded — but the default `MARKET_DATA_PROVIDER=mock`
    config still correctly reports it unavailable."""
    capabilities = client.get("/api/v1/capabilities").json()["data"]["capabilities"]
    assert capabilities["live_market_data"] is False


def test_capabilities_reports_live_market_data_true_when_a_real_provider_is_configured(
    client: TestClient,
) -> None:
    """Proves the flag is genuinely dynamic, not just always False under a
    different name — flips the already-bootstrapped app's own state flag
    (set by `app.bootstrap.build_market_data_provider`) directly, the same
    signal a real `MARKET_DATA_PROVIDER=yahoo_finance` deployment would
    produce, without needing a second full bootstrap."""
    client.app.state.market_data_provider_is_live = True
    try:
        capabilities = client.get("/api/v1/capabilities").json()["data"]["capabilities"]
        assert capabilities["live_market_data"] is True
    finally:
        client.app.state.market_data_provider_is_live = False


def test_capabilities_works_without_full_bootstrap(bare_client: TestClient) -> None:
    """`get_services_map` never raises even when nothing is configured —
    every entry is simply `None`, reported as unavailable."""
    response = bare_client.get("/api/v1/capabilities")

    assert response.status_code == status.HTTP_200_OK
    capabilities = response.json()["data"]["capabilities"]
    assert capabilities["screening"] is False


# --- /services -----------------------------------------------------------


def test_services_lists_every_wired_service(client: TestClient) -> None:
    services = client.get("/api/v1/services").json()["data"]["services"]
    names = {s["name"] for s in services}

    assert "risk_service" in names
    assert "backtesting_service" in names
    assert "explainability_service" in names


def test_services_reports_availability_true_when_constructed(client: TestClient) -> None:
    services = client.get("/api/v1/services").json()["data"]["services"]

    for entry in services:
        assert entry["available"] is True  # full bootstrap constructed every one


def test_services_reuses_health_check_service_for_construction_status(bare_client: TestClient) -> None:
    """`/services` depends on `HealthCheckService` (same as `/health`) —
    missing it must 503, not silently return an empty inventory."""
    response = bare_client.get("/api/v1/services")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
