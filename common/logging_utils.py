import os
import json
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta
from typing import Optional, TextIO

DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEFAULT_SUFFIX_FORMAT = "%y-%m-%d-%H-%M"


class NoRTFilter(logging.Filter):
    """Filter that removes RT-prefixed log lines from console handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            return not record.getMessage().startswith('RT ')
        except Exception:
            return True


class AlignedTimedFileHandler(logging.Handler):
    """Write logs into time-aligned folders/files without intermediary active file."""

    terminator = "\n"

    def __init__(
        self,
        log_dir: str,
        suffix_format: str,
        *,
        when: str = "H",
        interval: int = 1,
        encoding: str = "utf-8",
        utc: bool = False,
        file_extension: str = "log",
    ) -> None:
        super().__init__()
        self.log_dir = log_dir
        self.suffix_format = suffix_format
        self.when = when.upper()
        if self.when not in {"M", "H"}:
            raise ValueError("AlignedTimedFileHandler supports only 'M' or 'H' periods")
        self.interval = max(1, int(interval))
        self.encoding = encoding
        self.utc = utc
        self.file_extension = file_extension.lstrip(".") or "log"
        self.stream: Optional[TextIO] = None
        self.current_period_start: Optional[datetime] = None
        self.next_rollover: Optional[datetime] = None
        os.makedirs(self.log_dir, exist_ok=True)
        self.createLock()
        self._ensure_stream(initial=True)

    def _now(self) -> datetime:
        return datetime.utcnow() if self.utc else datetime.now()

    def _truncate(self, dt: datetime) -> datetime:
        if self.when == "H":
            return dt.replace(minute=0, second=0, microsecond=0)
        # self.when == "M"
        return dt.replace(second=0, microsecond=0)

    def _period_delta(self) -> timedelta:
        if self.when == "H":
            return timedelta(hours=self.interval)
        return timedelta(minutes=self.interval)

    def _compute_path(self, period_start: datetime) -> str:
        day_dir = os.path.join(self.log_dir, period_start.strftime("%Y-%m-%d"))
        os.makedirs(day_dir, exist_ok=True)
        suffix = period_start.strftime(self.suffix_format)
        return os.path.join(day_dir, f"{suffix}.{self.file_extension}")

    def _open_stream(self, period_start: datetime) -> None:
        if self.stream:
            try:
                self.stream.close()
            except Exception:
                pass
        path = self._compute_path(period_start)
        self.stream = open(path, mode="a", encoding=self.encoding)
        self.baseFilename = path  # type: ignore[attr-defined]
        self.current_period_start = period_start
        self.next_rollover = period_start + self._period_delta()

    def _ensure_stream(self, *, initial: bool = False) -> None:
        now = self._truncate(self._now())
        if (
            initial
            or self.current_period_start is None
            or self.next_rollover is None
            or now >= self.next_rollover
            or now < self.current_period_start
        ):
            self._open_stream(now)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with self.lock:
                self._ensure_stream()
                assert self.stream is not None
                self.stream.write(msg + self.terminator)
                self.stream.flush()
        except Exception:
            self.handleError(record)

    def flush(self) -> None:
        if self.stream and not self.stream.closed:
            try:
                self.stream.flush()
            except Exception:
                pass

    def close(self) -> None:
        try:
            if self.stream and not self.stream.closed:
                try:
                    self.stream.flush()
                except Exception:
                    pass
                self.stream.close()
            self.stream = None
        finally:
            super().close()


def _namer_factory(time_format: str, file_extension: str):
    extension = file_extension.lstrip(".") or "log"

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
        return os.path.join(day_folder, f"{suffix}.{extension}")

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
    file_extension: str = "log",
) -> logging.Handler:
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
    handler.namer = _namer_factory(suffix_format, file_extension)
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
    align_to_period_start: bool = False,
    use_utc: bool = False,
    file_extension: str = "log",
) -> TimedRotatingFileHandler:
    """Attach a rotating file handler with daily folders to the given logger."""

    if formatter is None:
        formatter = logging.Formatter(DEFAULT_LOG_FORMAT)

    if align_to_period_start:
        handler = AlignedTimedFileHandler(
            log_dir,
            suffix_format,
            when=when,
            interval=interval,
            encoding=encoding,
            utc=use_utc,
            file_extension=file_extension,
        )
    else:
        handler = create_daily_rotating_handler(
            log_dir,
            active_filename,
            when=when,
            interval=interval,
            suffix_format=suffix_format,
            encoding=encoding,
            backup_count=backup_count,
            file_extension=file_extension,
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
