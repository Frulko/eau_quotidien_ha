"""Coordinator de polling pour Eau Quotidien."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    AuthError,
    CommunicationError,
    EauQuotidienClient,
    MeterNotFoundError,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class EauQuotidienCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Récupère les données du compteur à intervalle régulier."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: EauQuotidienClient,
        meter_id: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{meter_id}",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client
        self.meter_id = meter_id

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.get_meter_data(self.meter_id)
        except AuthError as err:
            # Authentification cassée durablement → on remonte
            raise UpdateFailed(f"Authentification refusée: {err}") from err
        except (CommunicationError, MeterNotFoundError) as err:
            raise UpdateFailed(str(err)) from err
