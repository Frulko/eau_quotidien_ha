"""Constantes pour l'intégration Eau Quotidien."""
from datetime import timedelta

DOMAIN = "eau_quotidien"

CONF_BASE_URL = "base_url"
CONF_METER_ID = "meter_id"

DEFAULT_BASE_URL = "https://eau-quotidien.xxxx.fr"
DEFAULT_SCAN_INTERVAL = timedelta(hours=1)
