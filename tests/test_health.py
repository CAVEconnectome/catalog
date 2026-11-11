"""The cave-helm-charts catalog chart probes /catalog/health, and its ingress routes
/catalog to the service without stripping the prefix."""


async def test_health_is_served_under_prefix(client):
    resp = await client.get("/catalog/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_unprefixed_paths_are_not_served(client):
    resp = await client.get("/health")
    assert resp.status_code == 404


async def test_docs_and_static_are_served_under_prefix(client):
    assert (await client.get("/catalog/openapi.json")).status_code == 200
    assert (await client.get("/catalog/static/style.css")).status_code == 200
