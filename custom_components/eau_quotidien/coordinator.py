"""Coordinator de polling pour Eau Quotidien."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

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

    async def async_import_historical_stats(self) -> None:
        """Importe l'historique des relevés horaires dans les statistiques HA.

        Ne s'exécute qu'une seule fois par compteur.
        """
        flag_key = f"history_imported_{self.meter_id}"
        if self.hass.data.get(DOMAIN, {}).get(flag_key):
            return

        # Attendre que HA soit complètement démarré et que le recorder soit prêt
        await asyncio.sleep(30)

        # Récupérer le vrai entity_id du sensor via le registry
        registry = er.async_get(self.hass)
        unique_id = f"{self.meter_id}_index"
        statistic_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)

        if statistic_id is None:
            _LOGGER.error(
                "Impossible de trouver le sensor pour le compteur %s (unique_id=%s). "
                "L'import historique est annulé.",
                self.meter_id,
                unique_id,
            )
            return

        _LOGGER.info(
            "Import historique pour %s (statistic_id=%s)",
            self.meter_id,
            statistic_id,
        )

        try:
            all_reads: list[dict[str, Any]] = []
            now = datetime.now()

            # Récupérer les 6 derniers mois
            for i in range(6):
                year_month = (now - timedelta(days=30 * i)).strftime("%Y%m")
                try:
                    data = await self.client.get_meter_data_for_month(
                        self.meter_id, year_month
                    )
                    # Priorité aux relevés horaires pour Energy
                    reads = data.get("releves_horaire", [])
                    if not reads:
                        # Fallback sur les relevés journaliers
                        reads = data.get("reads", [])
                    if reads:
                        all_reads.extend(reads)
                        _LOGGER.debug(
                            "Mois %s: %d relevés récupérés", year_month, len(reads)
                        )
                except Exception as err:
                    _LOGGER.warning(
                        "Impossible de récupérer le mois %s: %s", year_month, err
                    )

            if not all_reads:
                _LOGGER.info("Aucun relevé historique trouvé")
                return

            # Dédupliquer par date/heure
            seen: set[str] = set()
            unique_reads: list[dict[str, Any]] = []
            for read in all_reads:
                dt_str = read.get("dt")
                if dt_str and dt_str not in seen:
                    seen.add(dt_str)
                    unique_reads.append(read)

            # Trier par date croissante
            sorted_reads = sorted(unique_reads, key=lambda x: x.get("dt", ""))

            # Construire les statistiques
            first_index: float | None = None
            stats: list[dict[str, Any]] = []

            for read in sorted_reads:
                dt_str = read.get("dt")
                index = read.get("index_releve")
                if dt_str is None or index is None:
                    continue

                start = self._parse_reading_date(dt_str)
                if start is None:
                    continue

                index_float = float(index)
                if first_index is None:
                    first_index = index_float

                cumulative_sum = index_float - first_index

                stats.append({
                    "start": start.isoformat(),
                    "state": index_float,
                    "sum": cumulative_sum,
                })

            if not stats:
                return

            await self.hass.services.async_call(
                "recorder",
                "import_statistics",
                {
                    "statistic_id": statistic_id,
                    "source": "recorder",
                    "unit_of_measurement": "m³",
                    "has_mean": False,
                    "has_sum": True,
                    "stats": stats,
                },
                blocking=True,
            )

            self.hass.data.setdefault(DOMAIN, {})[flag_key] = True
            _LOGGER.info(
                "Historique importé avec succès: %d points pour %s",
                len(stats),
                statistic_id,
            )

        except Exception as err:
            _LOGGER.error("Échec de l'import historique: %s", err)

    @staticmethod
    def _parse_reading_date(dt_str: str) -> datetime | None:
        """Parse une date de relevé (YYYY-MM-DD ou YYYY-MM-DD HH:MM:SS)."""
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                parsed = datetime.strptime(dt_str, fmt)
                return dt_util.as_utc(parsed)
            except ValueError:
                continue
        return None
