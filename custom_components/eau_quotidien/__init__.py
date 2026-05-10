"""Intégration Eau Quotidien (Nogema) pour Home Assistant."""
from __future__ import annotations

import asyncio
import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant

from .api import EauQuotidienClient
from .const import CONF_BASE_URL, CONF_METER_ID, DEFAULT_BASE_URL, DOMAIN
from .coordinator import EauQuotidienCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Met en place une instance de l'intégration."""
    # Session aiohttp dédiée à cette entry → cookie jar isolé par compte
    cookie_jar = aiohttp.CookieJar(unsafe=False)
    session = aiohttp.ClientSession(cookie_jar=cookie_jar)

    client = EauQuotidienClient(
        session,
        entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )

    coordinator = EauQuotidienCoordinator(hass, client, entry.data[CONF_METER_ID])
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "session": session,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Importer l'historique en arrière-plan (une seule fois)
    asyncio.create_task(coordinator.async_import_historical_stats(entry))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Décharge l'intégration et ferme la session HTTP."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        bag = hass.data[DOMAIN].pop(entry.entry_id)
        await bag["session"].close()
    return unload_ok
