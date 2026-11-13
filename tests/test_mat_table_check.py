"""Tests for check_mat_table: a materialization-sourced asset's source_table must be one of
the version's tables or views in MaterializationEngine."""

from __future__ import annotations

import httpx
import pytest

from cave_catalog.validation import check_mat_table

TABLES = ["synapses_pni_2", "nucleus_detection_v0"]
VIEWS = {
    "connections_with_nuclei": {"id": 2, "description": "connections"},
    "synapses_pni_2_in_out_degree": {"id": 1, "description": "degrees"},
}


# The routes ME really has: a version's tables under its v2 API, its views under v3 only
# (asking v2 for views is a 404, as it was on ltv7 when the check asked there).
TABLES_PATH = "/materialize/api/v2/datastack/minnie65_phase3_v1/version/1926/tables"
VIEWS_PATH = "/materialize/api/v3/datastack/minnie65_phase3_v1/version/1926/views"


def _transport(tables=TABLES, views=VIEWS, tables_status=200, views_status=200):
    """ME's /tables and /views for one version; records the paths asked for."""
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == TABLES_PATH:
            return httpx.Response(tables_status, json=tables)
        if request.url.path == VIEWS_PATH:
            return httpx.Response(views_status, json=views)
        return httpx.Response(404)

    return httpx.MockTransport(handler), seen


@pytest.fixture(autouse=True)
def _me(monkeypatch):
    monkeypatch.setenv("MAT_ENGINE_URL", "http://me:5000/materialize")
    from cave_catalog.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _check(name, transport):
    async with httpx.AsyncClient(transport=transport) as client:
        return await check_mat_table(
            "minnie65_phase3_v1", name, 1926, client, token="t"
        )


async def test_a_table_passes_without_asking_for_views():
    transport, seen = _transport()
    assert (await _check("synapses_pni_2", transport)).passed is True
    assert seen == [TABLES_PATH]


async def test_a_view_passes():
    transport, seen = _transport()
    assert (await _check("connections_with_nuclei", transport)).passed is True
    assert seen[-1] == VIEWS_PATH


async def test_views_listed_as_records_are_understood_too():
    transport, _ = _transport(
        views=[{"table_name": "connections_with_nuclei", "id": 2}]
    )
    assert (await _check("connections_with_nuclei", transport)).passed is True


async def test_neither_a_table_nor_a_view_fails():
    transport, _ = _transport()
    result = await _check("not_there", transport)
    assert result.passed is False
    assert "table or view 'not_there'" in result.message


async def test_views_unavailable_fails_like_a_missing_table():
    transport, _ = _transport(views_status=500)
    result = await _check("connections_with_nuclei", transport)
    assert result.passed is False
    assert "not found" in result.message


async def test_a_missing_version_still_fails():
    transport, seen = _transport(tables_status=404)
    result = await _check("connections_with_nuclei", transport)
    assert result.passed is False and "Version 1926 not found" in result.message
    assert all(p.endswith("/tables") for p in seen)
