"""Retired integration: importable compatibility surface, no transport."""
from operational_policy import require_operational_access


class BingXClient:
    def __init__(self, *args, **kwargs):
        require_operational_access("bingx_client")

    def request(self, *args, **kwargs):
        require_operational_access("bingx_transport")
