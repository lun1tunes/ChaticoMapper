import pytest


@pytest.mark.asyncio
async def test_root_endpoint_returns_app_info(client):
    response = await client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert "name" in payload
    assert "version" in payload


@pytest.mark.asyncio
async def test_health_endpoint_reports_status(client):
    response = await client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"healthy", "degraded", "unknown"}
    assert isinstance(payload["services"], dict)
