import pytest


@pytest.mark.asyncio
async def test_list_worker_apps_returns_empty(client):
    response = await client.get("/api/v1/worker-apps")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total"] == 0
