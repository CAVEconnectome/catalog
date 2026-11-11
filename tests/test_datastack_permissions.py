"""Tests for mapping datastacks to middle_auth datasets for permission checks."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from cave_catalog.auth.middleware import (
    AuthClient,
    AuthServiceError,
    AuthUser,
    _dataset_cache,
    has_datastack_permission,
)

AUTH_URL = "http://auth.test/auth"
LOOKUP_URL = f"{AUTH_URL}/api/v1/service/datastack/table/minnie65_public/dataset"


@pytest.fixture(autouse=True)
def _clear_cache():
    _dataset_cache.clear()
    yield
    _dataset_cache.clear()


@pytest.fixture
def settings():
    return SimpleNamespace(auth=SimpleNamespace(enabled=True, service_url=AUTH_URL))


@pytest.fixture
def auth_client(settings, monkeypatch):
    client = AuthClient(settings)
    monkeypatch.setattr("cave_catalog.auth.middleware._auth_client", client)
    return client


def _user(**kwargs) -> AuthUser:
    return AuthUser(user_id=1, email="u@test.com", token="user-token", **kwargs)


async def test_lookup_returns_dataset_and_caches(auth_client, httpx_mock):
    httpx_mock.add_response(url=LOOKUP_URL, json="minnie65_phase3")

    assert (
        await auth_client.dataset_for_datastack("minnie65_public", "user-token")
        == "minnie65_phase3"
    )
    # Served from the cache: a second request would have no response to match.
    assert (
        await auth_client.dataset_for_datastack("minnie65_public", "user-token")
        == "minnie65_phase3"
    )
    request = httpx_mock.get_request()
    assert request.headers["Authorization"] == "Bearer user-token"


async def test_lookup_returns_none_for_unknown_datastack(auth_client, httpx_mock):
    httpx_mock.add_response(url=LOOKUP_URL, status_code=404)

    assert await auth_client.dataset_for_datastack("minnie65_public", "t") is None
    assert "minnie65_public" not in _dataset_cache


async def test_lookup_raises_when_auth_service_unreachable(auth_client, httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("refused"), url=LOOKUP_URL)

    with pytest.raises(AuthServiceError):
        await auth_client.dataset_for_datastack("minnie65_public", "t")


async def test_permission_checked_on_mapped_dataset(auth_client, settings, httpx_mock):
    httpx_mock.add_response(url=LOOKUP_URL, json="minnie65_phase3", is_reusable=True)

    viewer = _user(permissions={"minnie65_phase3": ["view"]})
    assert await has_datastack_permission(viewer, settings, "minnie65_public", "view")
    assert not await has_datastack_permission(
        viewer, settings, "minnie65_public", "edit"
    )
    datastack_named = _user(permissions={"minnie65_public": ["view"]})
    assert not await has_datastack_permission(
        datastack_named, settings, "minnie65_public", "view"
    )


async def test_permission_returns_503_when_auth_service_unreachable(
    auth_client, settings, httpx_mock
):
    httpx_mock.add_exception(httpx.ConnectError("refused"), url=LOOKUP_URL)

    with pytest.raises(HTTPException) as exc_info:
        await has_datastack_permission(_user(), settings, "minnie65_public", "view")
    assert exc_info.value.status_code == 503
