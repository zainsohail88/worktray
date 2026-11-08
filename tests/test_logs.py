import io
import logging

from worktray.logs import SafeFormatter, escape, setup


def _capture() -> tuple[logging.Logger, io.StringIO]:
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(SafeFormatter("%(levelname)s %(name)s: %(message)s"))
    logger = logging.getLogger("worktray.test_logs")
    logger.handlers = [handler]
    logger.propagate = False
    return logger, output


def test_escape_shows_control_characters() -> None:
    assert escape("a\nb\r\tc\x1b[31m ") == "a\\nb\\r\\tc\\x1b[31m\\u2028"
    assert escape("plain text, café") == "plain text, café"


def test_a_line_break_in_an_argument_cannot_start_a_new_entry() -> None:
    logger, output = _capture()
    logger.warning("Drive export of %s failed", "doc-1\nERROR worktray: forged")
    assert output.getvalue() == "WARNING worktray.test_logs: Drive export of doc-1\\nERROR worktray: forged failed\n"


def test_traceback_lines_are_indented_and_escaped() -> None:
    logger, output = _capture()
    try:
        raise ValueError("bad\nERROR worktray: forged")
    except ValueError as error:
        logger.warning("Source %s failed", "jira", exc_info=error)
    first, *rest = output.getvalue().splitlines()
    assert first == "WARNING worktray.test_logs: Source jira failed"
    assert rest and all(line.startswith("    ") for line in rest)
    assert rest[-2:] == ["    ValueError: bad", "    ERROR worktray: forged"]
    assert not any(line.startswith("ERROR") for line in output.getvalue().splitlines())


def test_setup_adds_one_handler() -> None:
    logger = logging.getLogger("worktray")
    saved = (logger.handlers[:], logger.level, logger.propagate)
    try:
        logger.handlers = []
        setup()
        setup()
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0].formatter, SafeFormatter)
        assert logger.propagate is False
    finally:
        logger.handlers, logger.level, logger.propagate = saved
