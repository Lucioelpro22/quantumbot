"""Read-only successor commands; preserve historical harness.py fingerprints."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quantumbot_harness.core.safety_cli import main


if __name__ == "__main__":
    sys.exit(main())

