import json
import logging
import sys
from datetime import datetime, timezone

from app.core.config import settings

_AUDIT = "audit"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if isinstance(record.args, dict):
            payload.update(record.args)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level.upper())


def audit(action: str, **fields) -> None:
    """Structured audit trail: every recognition/attendance decision, device
    lifecycle change and enrollment lands here with the inputs that produced it.
    """
    logging.getLogger(_AUDIT).info(action, {"action": action, **fields})
