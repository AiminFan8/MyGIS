import json
import logging
import os
import sys
from typing import Optional

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    def __init__(self, *, default_fields=None):
        super().__init__()
        self.default_fields = default_fields or {}

    def format(self, record: logging.LogRecord) -> str:
        data = {
            **self.default_fields,
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            data["exc_info"] = self.formatException(record.exc_info)
        # Merge extra fields (those not in LogRecord default attrs)
        for k, v in record.__dict__.items():
            if k in (
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
            ):
                continue
            data.setdefault(k, v)
        return json.dumps(data, ensure_ascii=False)


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _coerce_level(value: Optional[str]) -> int:
    if value is None:
        return logging.INFO
    if isinstance(value, int):
        return value
    value = str(value).upper()
    return getattr(logging, value, logging.INFO)


def configure_logging(
    *,
    level: Optional[str | int] = None,
    json_format: Optional[bool] = None,
    file: Optional[str] = None,
    fmt: Optional[str] = None,
    datefmt: Optional[str] = None,
    reset: bool = False,
) -> None:
    """Configure root logging.

    Precedence: explicit args > env vars > defaults.

    Env vars:
    - MYGIS_LOG_LEVEL: e.g. DEBUG, INFO, WARNING
    - MYGIS_LOG_FORMAT: json|plain
    - MYGIS_LOG_FILE: path to log file (optional)
    """
    global _CONFIGURED

    if reset:
        for h in logging.root.handlers[:]:
            logging.root.removeHandler(h)
        _CONFIGURED = False

    if _CONFIGURED:
        return

    level = _coerce_level(level or os.getenv("MYGIS_LOG_LEVEL"))
    log_format_env = os.getenv("MYGIS_LOG_FORMAT", "plain").lower()
    json_format = json_format if json_format is not None else (log_format_env == "json")
    file = file if file is not None else os.getenv("MYGIS_LOG_FILE")

    handlers: list[logging.Handler] = []
    stream = logging.StreamHandler(stream=sys.stdout)
    if json_format:
        stream.setFormatter(JsonFormatter())
    else:
        stream.setFormatter(
            logging.Formatter(
                fmt or "%(levelname)s %(name)s: %(message)s",
                datefmt or "%Y-%m-%d %H:%M:%S",
            )
        )
    handlers.append(stream)

    if file:
        fh = logging.FileHandler(file)
        if json_format:
            fh.setFormatter(JsonFormatter())
        else:
            fh.setFormatter(
                logging.Formatter(
                    fmt or "%(asctime)s %(levelname)s %(name)s: %(message)s",
                    datefmt or "%Y-%m-%d %H:%M:%S",
                )
            )
        handlers.append(fh)

    logging.basicConfig(level=level, handlers=handlers)
    _CONFIGURED = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger; configure with defaults if needed."""
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)

