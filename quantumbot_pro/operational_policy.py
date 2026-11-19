"""Application capability denial, not a hostile-code sandbox.

No flag, environment variable or historical PASS can authorize operations.
"""


class OperationalBlocked(PermissionError):
    """No operational capability has been authorized."""


def require_operational_access(capability: str) -> None:
    raise OperationalBlocked(
        f"OPERATIONAL_BLOCKED:{capability}; LIVE_BLOCKED; "
        "FINAL_HOLDOUT_LOCKED; STOP_PERMANENT_DEVELOPMENT"
    )


def health_snapshot() -> dict:
    """Static metadata; never probes processes, credentials or datasets."""
    return {
        "schema_version": 1,
        "source": "published_engineering_policy",
        "live": "BLOCKED",
        "demo_paper_shadow": "BLOCKED",
        "research": "STOP_PERMANENT_DEVELOPMENT",
        "final_holdout": "LOCKED",
        "historical_holdout_integrity": "EXPOSED / CONTAMINATED",
        "runtime": "UNKNOWN",
        "runtime_observed_at": None,
        "independent_acceptance": "PENDING",
    }
