import os
import json
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from typing import Optional

DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEFAULT_SUFFIX_FORMAT = "%y-%m-%d-%H-%M"


class NoRTFilter(logging.Filter):
    """Filter that removes RT-prefixed log lines from console handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            return not record.getMessage().startswith('RT ')
        except Exception:
            return True


def _namer_factory(time_format: str):
    def _namer(default_name: str) -> str:
        base_dir, filename = os.path.split(default_name)
        parts = filename.split(".")
        suffix = parts[-1] if parts else ""
        try:
            dt = datetime.strptime(suffix, time_format)
        except ValueError:
            return default_name
        day_folder = os.path.join(base_dir, dt.strftime("%Y-%m-%d"))
        os.makedirs(day_folder, exist_ok=True)
        return os.path.join(day_folder, f"{suffix}.log")

    return _namer


def _rotator(source: str, dest: str) -> None:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.replace(source, dest)


def create_daily_rotating_handler(
    log_dir: str,
    active_filename: str,
    *,
    when: str = "M",
    interval: int = 1,
    suffix_format: str = DEFAULT_SUFFIX_FORMAT,
    encoding: str = "utf-8",
    backup_count: int = 0,
) -> TimedRotatingFileHandler:
    """Create a TimedRotatingFileHandler that stores rotated files under daily folders."""

    os.makedirs(log_dir, exist_ok=True)
    active_path = os.path.join(log_dir, active_filename)
    handler = TimedRotatingFileHandler(
        active_path,
        when=when,
        interval=interval,
        backupCount=backup_count,
        encoding=encoding,
    )
    handler.suffix = suffix_format
    handler.namer = _namer_factory(suffix_format)
    handler.rotator = _rotator
    return handler


def configure_rotating_logger(
    logger: logging.Logger,
    log_dir: str,
    active_filename: str,
    *,
    when: str = "M",
    interval: int = 1,
    suffix_format: str = DEFAULT_SUFFIX_FORMAT,
    formatter: Optional[logging.Formatter] = None,
    encoding: str = "utf-8",
    backup_count: int = 0,
) -> TimedRotatingFileHandler:
    """Attach a rotating file handler with daily folders to the given logger."""

    if formatter is None:
        formatter = logging.Formatter(DEFAULT_LOG_FORMAT)

    handler = create_daily_rotating_handler(
        log_dir,
        active_filename,
        when=when,
        interval=interval,
        suffix_format=suffix_format,
        encoding=encoding,
        backup_count=backup_count,
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return handler


def log_event(
    logger: logging.Logger,
    event: str,
    level: int = logging.INFO,
    *,
    exc_info=None,
    **fields,
) -> None:
    """Log a structured event payload as JSON."""

    payload = {"evt": event, "ts": datetime.utcnow().isoformat() + "Z", **fields}
    message = json.dumps(payload, ensure_ascii=False)
    logger.log(level, message, exc_info=exc_info)
