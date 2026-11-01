"""Where a browser sign-in link goes.

From the terminal, the link opens in the default browser and is printed as a fallback. From the
Settings page, the server may have no display at all (a systemd or launchd service), so the link is
handed to the page instead and the person opens it in the browser they are already using.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
import webbrowser

_handler: ContextVar[Callable[[str], None] | None] = ContextVar("sign_in_handler", default=None)


def open_sign_in(url: str, label: str) -> None:
    """Send the person to a sign-in page. Context variables follow asyncio.to_thread, so threads see the page's handler."""
    handler = _handler.get()
    if handler is not None:
        handler(url)
        return
    print(f"{label}: approve access in your browser.")
    if not webbrowser.open(url):
        print(f"Open this sign-in link: {url}")


@contextmanager
def hand_links_to(handler: Callable[[str], None]) -> Iterator[None]:
    """Within this block, sign-in links go to the handler instead of a browser on the server."""
    token = _handler.set(handler)
    try:
        yield
    finally:
        _handler.reset(token)
