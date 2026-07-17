import logging
import re
import sys
from typing import TextIO

DATE_FORMAT = "%H:%M:%S"
PYMAX_HANDLER_ATTR = "_pymax_pretty_handler"

RESET = "\x1b[0m"
DIM = "\x1b[2m"
BOLD = "\x1b[1m"

LEVEL_STYLES = {
    logging.DEBUG: ("\x1b[90m", "DEBUG"),
    logging.INFO: ("\x1b[36m", "INFO"),
    logging.WARNING: ("\x1b[33m", "WARN"),
    logging.ERROR: ("\x1b[31m", "ERROR"),
    logging.CRITICAL: ("\x1b[1;37;41m", "CRIT"),
}

LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "FATAL": logging.FATAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}


class PrettyFormatter(logging.Formatter):
    def __init__(self, *, use_colors: bool = True) -> None:
        super().__init__()
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        color, level = LEVEL_STYLES.get(record.levelno, ("", "???"))

        time = self.formatTime(record, DATE_FORMAT)
        message = record.getMessage()

        line = f"{DIM}{time}{RESET} {color}{BOLD}{level}{RESET} {message}"

        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)

        if not self.use_colors:
            line = _strip_ansi(line)

        return line


def configure_logging(
    level: int | str = logging.INFO,
    *,
    stream: TextIO | None = None,
    use_colors: bool | None = None,
    force: bool = False,
) -> None:
    """Настраивает pretty-логи для logger-а ``pymax``.

    Обычно уровень логов задают через ``ExtraConfig(log_level="DEBUG")``.
    PyMax ставит свой handler только если приложение еще не настроило logging.
    Вызывайте эту функцию с ``force=True``, если хотите принудительно включить
    pretty-логи PyMax.

    Args:
        level: Уровень логирования: строка вроде ``"DEBUG"`` или число из
            модуля ``logging``.
        stream: Поток для вывода. По умолчанию ``sys.stderr``.
        use_colors: Включить ANSI-цвета. Если ``None``, определяется по TTY.
        force: Заменить существующие handler-ы logger-а ``pymax`` на pretty
            handler PyMax.

    Returns:
        ``None``.

    Example:
        .. code-block:: python

           from pymax import configure_logging

           configure_logging("DEBUG", use_colors=False)
    """
    stream = stream or sys.stderr
    if stream is None:
        raise RuntimeError("No logging stream is available")

    if use_colors is None:
        use_colors = hasattr(stream, "isatty") and stream.isatty()

    logger = logging.getLogger("pymax")
    level_value = _normalize_level(level)
    logger.setLevel(level_value)

    if not force and _logging_already_configured(logger):
        if logging.getLogger().handlers and not _has_non_null_handlers(logger):
            logger.propagate = True
        return

    logger.handlers.clear()
    logger.propagate = False

    handler = logging.StreamHandler(stream)
    handler.setLevel(level_value)
    handler.setFormatter(
        PrettyFormatter(
            use_colors=use_colors,
        )
    )
    setattr(handler, PYMAX_HANDLER_ATTR, True)

    logger.addHandler(handler)


def get_logger(name: str | None = None) -> logging.Logger:
    if not name:
        return logging.getLogger("pymax")

    if name.startswith("pymax"):
        return logging.getLogger(name)

    return logging.getLogger(f"pymax.{name}")


def _normalize_level(level: int | str) -> int:
    if isinstance(level, int):
        return level

    value = LEVELS.get(level.upper())

    if isinstance(value, int):
        return value

    raise ValueError(f"Unknown log level: {level}")


def _strip_ansi(text: str) -> str:

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _logging_already_configured(logger: logging.Logger) -> bool:
    return bool(logging.getLogger().handlers or _has_external_handlers(logger))


def _has_non_null_handlers(logger: logging.Logger) -> bool:
    return any(not isinstance(handler, logging.NullHandler) for handler in logger.handlers)


def _has_external_handlers(logger: logging.Logger) -> bool:
    return any(
        not isinstance(handler, logging.NullHandler)
        and not getattr(handler, PYMAX_HANDLER_ATTR, False)
        for handler in logger.handlers
    )


logging.getLogger("pymax").addHandler(logging.NullHandler())
