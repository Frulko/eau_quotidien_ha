"""Config flow Eau Quotidien : entrée des identifiants + sélection compteur."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult

from .api import (
    AuthError,
    CommunicationError,
    EauQuotidienClient,
    MeterNotFoundError,
)
from .const import (
    CONF_BASE_URL,
    CONF_METER_ID,
    DEFAULT_BASE_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
    }
)


class EauQuotidienConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Flow de config en deux étapes : identifiants → choix du compteur."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._password: str | None = None
        self._base_url: str = DEFAULT_BASE_URL
        self._meter_ids: list[int] = []
        self._designations: dict[int, str] = {}

    # ------------------------------------------------------------------
    # Étape 1 : identifiants
    # ------------------------------------------------------------------
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]
            self._base_url = user_input.get(CONF_BASE_URL, DEFAULT_BASE_URL)

            # On crée une session jetable pour le test (cookie jar isolé)
            jar = aiohttp.CookieJar(unsafe=False)
            async with aiohttp.ClientSession(cookie_jar=jar) as session:
                client = EauQuotidienClient(
                    session, self._base_url, self._email, self._password
                )
                try:
                    await client.login()
                    self._meter_ids = await client.discover_meters()

                    # On essaie de récupérer la désignation pour chaque compteur
                    for mid in self._meter_ids:
                        try:
                            data = await client.get_meter_data(mid)
                            meter = data.get("meter") or {}
                            self._designations[mid] = (
                                meter.get("designation") or str(mid)
                            )
                        except (CommunicationError, MeterNotFoundError):
                            self._designations[mid] = str(mid)
                except AuthError as err:
                    _LOGGER.warning("Auth refusée: %s", err)
                    errors["base"] = "invalid_auth"
                except CommunicationError as err:
                    _LOGGER.warning("Comm error: %s", err)
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Erreur inattendue lors de la validation")
                    errors["base"] = "unknown"

            if not errors:
                if not self._meter_ids:
                    errors["base"] = "no_meters"
                elif len(self._meter_ids) == 1:
                    return await self._async_create(self._meter_ids[0])
                else:
                    return await self.async_step_meter()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Étape 2 (si plusieurs compteurs) : choix
    # ------------------------------------------------------------------
    async def async_step_meter(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return await self._async_create(int(user_input[CONF_METER_ID]))

        choices = {
            str(mid): f"{self._designations.get(mid, mid)} (ID {mid})"
            for mid in self._meter_ids
        }
        schema = vol.Schema(
            {vol.Required(CONF_METER_ID): vol.In(choices)}
        )
        return self.async_show_form(step_id="meter", data_schema=schema)

    # ------------------------------------------------------------------
    # Création de l'entry
    # ------------------------------------------------------------------
    async def _async_create(self, meter_id: int) -> FlowResult:
        await self.async_set_unique_id(f"{DOMAIN}_{meter_id}")
        self._abort_if_unique_id_configured()

        designation = self._designations.get(meter_id, str(meter_id))
        return self.async_create_entry(
            title=f"Compteur {designation}",
            data={
                CONF_EMAIL: self._email,
                CONF_PASSWORD: self._password,
                CONF_BASE_URL: self._base_url,
                CONF_METER_ID: meter_id,
            },
        )
