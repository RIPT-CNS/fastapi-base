import json
import logging
import logging.config
from contextvars import ContextVar

from app.core.config import settings

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    handler = {
        "class": "logging.StreamHandler",
        "stream": "ext://sys.stdout",
        "formatter": "json" if settings.LOG_JSON else "text",
        "filters": ["request_id"],
    }
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {
                "text": {
                    "format": "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"
                },
                "json": {"()": JsonFormatter},
            },
            "handlers": {"console": handler},
            "root": {"level": settings.LOG_LEVEL, "handlers": ["console"]},
            "loggers": {
                "uvicorn": {"level": "INFO", "handlers": ["console"], "propagate": False},
                # Access logs are written by RequestContextMiddleware (with request id + duration)
                "uvicorn.access": {"level": "WARNING", "handlers": [], "propagate": False},
                "sqlalchemy.engine": {"level": "INFO" if settings.DB_ECHO else "WARNING"},
            },
        }
    )
