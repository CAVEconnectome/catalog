"""Tests for cave_catalog.routers.helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cave_catalog.routers.helpers import (
    asset_is_expired,
    get_asset,
    now_utc,
    require_asset_view_access,
    require_datastack_permission,
)

# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_settings(auth_enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(auth=SimpleNamespace(enabled=auth_enabled))


def _make_user(
    *,
    permissions: dict | None = None,
    groups: list | None = None,
    is_admin: bool = False,
) -> SimpleNamespace:
    from cave_catalog.auth.middleware import AuthUser

    return AuthUser(
        user_id=1,
        email="test@example.com",
        permissions=permissions or {},
        groups=groups or [],
        is_admin=is_admin,
    )


def _make_asset(
    *,
    datastack: str = "minnie65",
    access_group: str | None = None,
    expires_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        datastack=datastack,
        access_group=access_group,
        expires_at=expires_at,
    )


# ---------------------------------------------------------------------------
# now_utc / asset_is_expired
# ---------------------------------------------------------------------------


def test_now_utc_is_aware():
    t = now_utc()
    assert t.tzinfo is not None


def test_asset_not_expired_when_no_expiry():
    asset = _make_asset()
    assert not asset_is_expired(asset)


def test_asset_expired_in_past():
    asset = _make_asset(expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert asset_is_expired(asset)


def test_asset_not_expired_in_future():
    future = now_utc() + timedelta(days=1)
    asset = _make_asset(expires_at=future)
    assert not asset_is_expired(asset)


# ---------------------------------------------------------------------------
# require_datastack_permission
# ---------------------------------------------------------------------------

# middle_auth grants permissions on datasets; each datastack maps to one.
DATASETS = {"ds1": "ds1_dataset", "minnie65": "minnie65_dataset"}


@pytest.fixture(autouse=True)
def dataset_lookup(monkeypatch):
    from cave_catalog.auth.middleware import AuthClient

    lookup = AsyncMock(side_effect=lambda datastack, token: DATASETS.get(datastack))
    monkeypatch.setattr(AuthClient, "dataset_for_datastack", lookup)
    return lookup


async def test_permission_passes_when_auth_disabled():
    user = _make_user()
    settings = _make_settings(auth_enabled=False)
    # Should not raise
    await require_datastack_permission(user, settings, "any_ds", "edit")


async def test_permission_passes_when_user_has_perm_on_dataset():
    user = _make_user(permissions={"ds1_dataset": ["edit"]})
    settings = _make_settings()
    await require_datastack_permission(user, settings, "ds1", "edit")


async def test_permission_on_datastack_name_is_not_enough():
    from fastapi import HTTPException

    user = _make_user(permissions={"ds1": ["edit"]})
    settings = _make_settings()
    with pytest.raises(HTTPException) as exc_info:
        await require_datastack_permission(user, settings, "ds1", "edit")
    assert exc_info.value.status_code == 403


async def test_permission_raises_403_for_unmapped_datastack():
    from fastapi import HTTPException

    user = _make_user(permissions={"unknown_ds": ["edit"]})
    settings = _make_settings()
    with pytest.raises(HTTPException) as exc_info:
        await require_datastack_permission(user, settings, "unknown_ds", "edit")
    assert exc_info.value.status_code == 403


async def test_permission_raises_403_on_missing_edit():
    from fastapi import HTTPException

    user = _make_user(permissions={"ds1_dataset": ["view"]})
    settings = _make_settings()
    with pytest.raises(HTTPException) as exc_info:
        await require_datastack_permission(user, settings, "ds1", "edit")
    assert exc_info.value.status_code == 403
    assert "Write permission" in exc_info.value.detail


async def test_permission_raises_403_on_missing_view():
    from fastapi import HTTPException

    user = _make_user(permissions={})
    settings = _make_settings()
    with pytest.raises(HTTPException) as exc_info:
        await require_datastack_permission(user, settings, "ds1", "view")
    assert exc_info.value.status_code == 403
    assert "Read permission" in exc_info.value.detail


async def test_permission_passes_for_admin_without_lookup(dataset_lookup):
    user = _make_user(is_admin=True)
    settings = _make_settings()
    await require_datastack_permission(user, settings, "any_ds", "edit")
    dataset_lookup.assert_not_awaited()


# ---------------------------------------------------------------------------
# require_asset_access
# ---------------------------------------------------------------------------


async def test_asset_access_passes_when_auth_disabled():
    user = _make_user()
    settings = _make_settings(auth_enabled=False)
    asset = _make_asset()
    await require_asset_view_access(user, settings, asset)


async def test_asset_access_passes_with_permission_on_datastack_dataset():
    user = _make_user(permissions={"minnie65_dataset": ["view"]})
    settings = _make_settings()
    asset = _make_asset(datastack="minnie65")
    await require_asset_view_access(user, settings, asset)


async def test_asset_access_passes_with_permission_on_access_group():
    user = _make_user(permissions={"my_group": ["view"]})
    settings = _make_settings()
    asset = _make_asset(datastack="minnie65", access_group="my_group")
    await require_asset_view_access(user, settings, asset)


async def test_asset_access_with_access_group_ignores_datastack_permission():
    from fastapi import HTTPException

    user = _make_user(permissions={"minnie65_dataset": ["view"]})
    settings = _make_settings()
    asset = _make_asset(datastack="minnie65", access_group="my_group")
    with pytest.raises(HTTPException) as exc_info:
        await require_asset_view_access(user, settings, asset)
    assert exc_info.value.status_code == 403


async def test_asset_access_passes_with_group_membership():
    user = _make_user(groups=["minnie65"])
    settings = _make_settings()
    asset = _make_asset(datastack="minnie65")
    await require_asset_view_access(user, settings, asset)


async def test_asset_access_raises_403_when_denied():
    from fastapi import HTTPException

    user = _make_user(permissions={}, groups=[])
    settings = _make_settings()
    asset = _make_asset(datastack="minnie65")
    with pytest.raises(HTTPException) as exc_info:
        await require_asset_view_access(user, settings, asset)
    assert exc_info.value.status_code == 403
    assert "Access denied" in exc_info.value.detail


async def test_asset_access_passes_for_admin():
    user = _make_user(is_admin=True)
    settings = _make_settings()
    asset = _make_asset(datastack="minnie65")
    await require_asset_view_access(user, settings, asset)


# ---------------------------------------------------------------------------
# get_asset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_asset_returns_asset():
    from cave_catalog.db.models import Asset

    asset_id = uuid.uuid4()
    mock_asset = _make_asset()
    mock_asset.expires_at = None

    session = AsyncMock()
    session.get = AsyncMock(return_value=mock_asset)

    result = await get_asset(session, asset_id)
    assert result is mock_asset
    session.get.assert_awaited_once_with(Asset, asset_id)


@pytest.mark.asyncio
async def test_get_asset_raises_404_when_missing():
    from fastapi import HTTPException

    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_asset(session, uuid.uuid4())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_asset_raises_404_when_expired():
    from fastapi import HTTPException

    expired = _make_asset(expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    session = AsyncMock()
    session.get = AsyncMock(return_value=expired)

    with pytest.raises(HTTPException) as exc_info:
        await get_asset(session, uuid.uuid4())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_asset_ignores_expiry_when_check_expired_false():
    expired = _make_asset(expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    session = AsyncMock()
    session.get = AsyncMock(return_value=expired)

    result = await get_asset(session, uuid.uuid4(), check_expired=False)
    assert result is expired
