"""Log line ingestion and schema validation."""
import json

REQUIRED_KEYS = {"id", "svc", "phase", "ts", "status"}
VALID_SERVICES = {"auth", "gateway", "payment"}
VALID_PHASES = {"start", "end"}


def parse_event(line):
    """Parse a single raw log line into an event dict.

    Returns the event dict for a valid line, or None for a malformed line.
    """
    try:
        obj = json.loads(line)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    if not REQUIRED_KEYS.issubset(obj.keys()):
        return None
    if obj["svc"] not in VALID_SERVICES or obj["phase"] not in VALID_PHASES:
        return None
    if not isinstance(obj["id"], str) or not obj["id"]:
        return None
    if not isinstance(obj["ts"], int) or obj["ts"] < 0:
        return None
    if not isinstance(obj["status"], int) or not (100 <= obj["status"] <= 599):
        return None
    return obj
