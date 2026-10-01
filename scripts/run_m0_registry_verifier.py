"""Run the additive, read-only M0 registry verifier."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantumbot_harness.core.m0_gate_verifier import verify_registry


if __name__ == "__main__":
    result = verify_registry(Path(__file__).resolve().parents[1])
    print(json.dumps(result, indent=2, sort_keys=True))
    # A clean registry is only review-ready, never a formal PASS.
    sys.exit(0 if result["status"] == "READY_FOR_INDEPENDENT_REVIEW" else 1)

