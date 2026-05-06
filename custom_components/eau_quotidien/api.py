"""Client async pour la plateforme Eau Quotidien (Nogema)."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

import aiohttp
from yarl import URL

_LOGGER = logging.getLogger(__name__)


class EauQuotidienError(Exception):
    """Erreur de base."""


class AuthError(EauQuotidienError):
    """Identifiants invalides ou session refusée."""


class CommunicationError(EauQuotidienError):
    """Problème réseau / serveur injoignable."""


class MeterNotFoundError(EauQuotidienError):
    """Compteur inconnu pour ce compte."""


class EauQuotidienClient:
    """Client minimal qui parle à la plateforme Nogema (Eau Quotidien).

    L'API n'est pas publique : on parse les blocs ``JSON.parse('...')``
    embarqués dans le HTML de la page ``/meter``.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        email: str,
        password: str,
    ) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._email = email
        self._password = password
        self._authenticated = False

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    async def login(self) -> None:
        """S'authentifie. Lève AuthError ou CommunicationError."""
        # Pose le cookie de langue (l'app le fait au premier GET)
        self._session.cookie_jar.update_cookies(
            {"lang": "fr"}, response_url=URL(self._base)
        )
        try:
            async with self._session.post(
                f"{self._base}/login",
                data={
                    "email": self._email,
                    "password": self._password,
                    "remember_me": "0",
                    "captcha": "",
                },
                headers={
                    "x-requested-with": "XMLHttpRequest",
                    "origin": self._base,
                    "accept": "*/*",
                },
            ) as resp:
                if resp.status not in (200, 204, 302):
                    raise AuthError(f"Login refusé (HTTP {resp.status})")

            # Vérifie qu'on a bien récupéré un cookie de session
            cookies = self._session.cookie_jar.filter_cookies(URL(self._base))
            if "sess" not in cookies:
                raise AuthError(
                    "Login accepté mais aucun cookie de session retourné"
                )
            self._authenticated = True
            _LOGGER.debug("Login OK pour %s", self._email)
        except aiohttp.ClientError as err:
            raise CommunicationError(f"Erreur réseau au login: {err}") from err

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------
    async def _get_meter_html(
        self,
        meter_id: int,
        mode: int = 3,
        date: str | None = None,
    ) -> str:
        if date is None:
            date = datetime.now().strftime("%Y%m")
        url = f"{self._base}/meter?id={meter_id}&mode={mode}&date={date}"

        async def _fetch() -> str:
            async with self._session.get(
                url,
                headers={"x-requested-with": "KnNav", "accept": "*/*"},
            ) as resp:
                return await resp.text()

        try:
            html = await _fetch()
        except aiohttp.ClientError as err:
            raise CommunicationError(f"Erreur réseau: {err}") from err

        # Si on n'a pas de bloc JSON.parse → session expirée → on (re)logge
        if "JSON.parse" not in html:
            _LOGGER.debug("Pas de JSON dans la page → tentative de login")
            await self.login()
            try:
                html = await _fetch()
            except aiohttp.ClientError as err:
                raise CommunicationError(f"Erreur réseau: {err}") from err
            if "JSON.parse" not in html:
                raise MeterNotFoundError(
                    f"Compteur {meter_id} introuvable ou inaccessible"
                )
        return html

    async def get_meter_data(self, meter_id: int) -> dict[str, Any]:
        """Récupère et parse les données pour un compteur donné."""
        html = await self._get_meter_html(meter_id)
        return self._parse_html(html)

    async def discover_meters(self) -> list[int]:
        """Découvre les IDs des compteurs accessibles au compte courant.

        On tente d'abord la page d'accueil, puis on scanne plusieurs patterns.
        Suppose qu'un login a déjà été fait.
        """
        try:
            async with self._session.get(
                f"{self._base}/",
                headers={"x-requested-with": "KnNav", "accept": "*/*"},
            ) as resp:
                html = await resp.text()
        except aiohttp.ClientError as err:
            raise CommunicationError(f"Erreur réseau: {err}") from err

        ids: set[int] = set()
        for m in re.finditer(r"meters\s*:\s*JSON\.parse\('([^']*)'\)", html):
            try:
                for x in json.loads(m.group(1)):
                    ids.add(int(x))
            except (ValueError, json.JSONDecodeError):
                continue
        for m in re.finditer(r"/meter\?id=(\d+)", html):
            ids.add(int(m.group(1)))
        for m in re.finditer(r"\bopen\((\d{4,})\b", html):
            ids.add(int(m.group(1)))

        return sorted(ids)

    # ------------------------------------------------------------------
    # HTML parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_html(html: str) -> dict[str, Any]:
        def _extract(key: str) -> Any:
            m = re.search(
                rf"{key}\s*:\s*JSON\.parse\('([^']*)'\)", html
            )
            if not m:
                return None
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                return None

        data: dict[str, Any] = {
            "meter": _extract("meter"),
            "reads": _extract("reads") or [],
            "releves_horaire": _extract("releves_horaire") or [],
        }

        for field, regex in (
            ("conso_avg", r"<span id=conso_avg>(\d+)</span>"),
            ("last_conso", r"<text id=last_conso_value[^>]*>(\d+)</text>"),
            ("threshold_low", r"<text id=last_conso_b[^>]*>(\d+)</text>"),
            ("threshold_high", r"<text id=last_conso_h[^>]*>(\d+)</text>"),
        ):
            m = re.search(regex, html)
            if m:
                data[field] = int(m.group(1))

        if data["reads"]:
            data["latest"] = data["reads"][0]

        return data
