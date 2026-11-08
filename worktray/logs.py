"""Log output that text from a connected service cannot forge.

Error messages and IDs from services end up in log lines. A line break in them could start what looks
like a new log entry, so every entry is one line and the lines of a traceback are indented below it.
"""

import logging
import re

CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def escape(text: str) -> str:
    """Show line breaks and other control characters as escapes, such as \\n."""
    return CONTROL.sub(lambda match: match.group().encode("unicode_escape").decode("ascii"), text)


class SafeFormatter(logging.Formatter):
    """Escapes the message and indents each line of a traceback, so only a real entry starts a line."""

    def formatMessage(self, record: logging.LogRecord) -> str:
        return escape(super().formatMessage(record))

    def formatException(self, ei: object) -> str:
        return "\n".join("    " + escape(line) for line in super().formatException(ei).splitlines())

    def formatStack(self, stack_info: str) -> str:
        return "\n".join("    " + escape(line) for line in stack_info.splitlines())


def setup(level: int = logging.WARNING) -> None:
    """Send worktray's log entries to standard error through SafeFormatter, once."""
    logger = logging.getLogger("worktray")
    if any(isinstance(handler.formatter, SafeFormatter) for handler in logger.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(SafeFormatter(FORMAT))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
