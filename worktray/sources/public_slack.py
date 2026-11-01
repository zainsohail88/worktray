"""Read public Slack through an MCP server that indexes it.

The server is whatever your organisation runs; the URL and tool name are settings. The tool must
take `query`, `source_types` and `time_cutoff` and return `results`, each with `content`, `url`
and `updated_at`. Private channels and direct
messages are never read this way; those come through the Codex Slack bridge.

The MCP client library is the optional `mcp` extra, so it is imported only when used.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import logging
import re
import shutil
import warnings

import httpx

from worktray import APP_NAME, install_command
from worktray.auth.browser import open_sign_in
from worktray.auth.mcp_tokens import KeyringTokens, refresh_due
from worktray.config import Setting, plain_text, single_name, web_url
from worktray.models import Batch, Item
from worktray.paths import oauth_dir
from worktray.references import find_references
from worktray.sources.errors import NotConnectedError, SignInRequired, SourceError
from worktray.sources.extract import ASK
from worktray.sources.sessions import short_title
from worktray.store import Store

PUBLIC_SLACK_MCP_URL = Setting(
    "public_slack_mcp_url", "Slack search server URL", help="An MCP server your team runs that can search public Slack channels.", placeholder="https://mcp.example.com/mcp", validate=web_url
)
PUBLIC_SLACK_MCP_TOOL = Setting("public_slack_mcp_tool", "Search tool name", help="The tool on that server that searches Slack messages.", placeholder="search_documents", validate=single_name)
SLACK_DISPLAY_NAME = Setting(
    "slack_display_name", "Your name in Slack", help="As people @-mention you, such as Sam Lee. Leave blank to use your Jira name.", placeholder="Sam Lee", validate=plain_text
)
FIELDS = (PUBLIC_SLACK_MCP_URL, PUBLIC_SLACK_MCP_TOOL, SLACK_DISPLAY_NAME)
MENTION_QUERIES = ("@{name} can you", "@{name} please review", "@{name} could you help", "@{name} any update")
MISSING_EXTRA = f"This needs an extra package. Run {install_command(('mcp',))}"


def mcp_available() -> bool:
    return importlib.util.find_spec("fastmcp") is not None


def _mcp():
    """Import the MCP client lazily, quieting the deprecation warnings its dependencies emit."""
    if not mcp_available():
        raise NotConnectedError(MISSING_EXTRA)
    # Only the import is quieted; deprecations raised later anywhere else still show.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from fastmcp import Client
        from fastmcp.client.auth import OAuth
        from fastmcp.client.transports import StreamableHttpTransport
        from fastmcp.exceptions import ClientError, ToolError
    return Client, OAuth, StreamableHttpTransport, (ClientError, ToolError, TimeoutError, OSError, httpx.HTTPError, RuntimeError)


def _url(store: Store) -> str:
    url = PUBLIC_SLACK_MCP_URL.read(store)
    if not url:
        raise NotConnectedError("Not set up yet. Add the URL of your team's Slack search MCP server in Settings.")
    return url


def _oauth(url: str, browser: bool):
    _, OAuth, _, _ = _mcp()

    class SavedGrant(OAuth):
        async def _initialize(self) -> None:
            """Refresh a token that is close to expiring before it is used, rather than after it is refused."""
            await super()._initialize()
            tokens = self.context.current_tokens
            if tokens and tokens.refresh_token and refresh_due(self.context.token_expiry_time):
                # A time in the past; 0 would mean "never expires".
                self.context.token_expiry_time = 1.0

    class StoredOAuth(SavedGrant):
        """Refuse a new browser login during refresh and status checks."""

        async def redirect_handler(self, authorization_url: str) -> None:
            raise SignInRequired("Sign in to the Slack search server first, from Settings.")

    class BrowserOAuth(SavedGrant):
        """Send the sign-in link to the Settings page or the terminal's browser."""

        async def redirect_handler(self, authorization_url: str) -> None:
            open_sign_in(authorization_url, "Public Slack")

    # Earlier builds kept this grant as plain files; remove them now that it lives in the keyring.
    shutil.rmtree(oauth_dir() / "fastmcp", ignore_errors=True)
    kind = BrowserOAuth if browser else StoredOAuth
    return kind(
        url,
        client_name=APP_NAME,
        token_storage=KeyringTokens(),
        scopes="openid email offline_access",
        additional_client_metadata={"token_endpoint_auth_method": "none"},
        httpx_client_factory=_http_client,
    )


async def _user_agent(request: httpx.Request) -> None:
    """Discovery requests omit the client user agent, and some gateways answer those with 403."""
    if not request.headers.get("user-agent", "").strip():
        request.headers["User-Agent"] = APP_NAME


def _http_client(headers: dict[str, str] | None = None, timeout: httpx.Timeout | None = None, auth: httpx.Auth | None = None, **kwargs: object) -> httpx.AsyncClient:
    merged = {"User-Agent": APP_NAME, **(headers or {})}
    if not merged.get("User-Agent", "").strip():
        merged["User-Agent"] = APP_NAME
    return httpx.AsyncClient(headers=merged, timeout=timeout, auth=auth, follow_redirects=bool(kwargs.get("follow_redirects")), event_hooks={"request": [_user_agent]})


def _client(url: str, browser: bool):
    Client, _, StreamableHttpTransport, _ = _mcp()
    return Client(StreamableHttpTransport(url, headers={"User-Agent": APP_NAME}, auth=_oauth(url, browser), httpx_client_factory=_http_client), timeout=180)


def _sign_in_error(error: BaseException) -> SourceError | None:
    seen: set[int] = set()
    pending = [error]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, SourceError):
            return current
        pending.extend(getattr(current, "exceptions", ()))
        if current.__cause__:
            pending.append(current.__cause__)
        if current.__context__:
            pending.append(current.__context__)
    return None


async def probe(url: str, browser: bool = False) -> None:
    """Open a session. Browser sign-in happens only when browser is true."""
    connection_errors = _mcp()[3]
    auth_log = logging.getLogger("mcp.client.auth.oauth2")
    level = auth_log.level
    if not browser:
        auth_log.setLevel(logging.CRITICAL)
    try:
        async with _client(url, browser) as mcp:
            await mcp.list_tools()
    except SourceError:
        raise
    except connection_errors as error:
        sign_in = _sign_in_error(error)
        if sign_in:
            raise sign_in from error
        raise SourceError("Couldn't connect to the Slack search server. Check the URL and that you're online.") from error
    finally:
        auth_log.setLevel(level)


async def check_public_slack(store: Store) -> str:
    await probe(_url(store), False)
    return "Connected to the Slack search server"


async def connect_public_slack(store: Store) -> str:
    """Sign in in the browser. A saved grant that still works is kept, so a cancelled sign-in loses nothing."""
    await probe(_url(store), True)
    return "Signed in to the Slack search server"


async def disconnect_public_slack(store: Store) -> str:
    """Forget the saved sign-in without contacting the server."""
    await _oauth(_url(store), True).token_storage_adapter.clear()
    return "Signed out of the Slack search server"


async def read_public_slack(store: Store) -> Batch:
    """Propose public Slack threads that @-mention you with an ask.

    The search returns ten rows per query with no paging, so several phrasings aimed at you are merged.
    """
    url = _url(store)
    connection_errors = _mcp()[3]
    tool = PUBLIC_SLACK_MCP_TOOL.read(store)
    if not tool:
        raise NotConnectedError("Not set up yet. Add the name of the server's search tool in Settings.")
    name = SLACK_DISPLAY_NAME.read(store) or store.setting("display_name").strip()
    if not name:
        raise NotConnectedError("Not set up yet. Add your name in Slack in Settings, so worktray can find mentions of you.")
    # Slack renders mentions with the display name, which is usually the full or first name.
    mention = re.compile(r"@(?:" + "|".join(map(re.escape, {name, name.split()[0]})) + r")\b", re.I)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00Z")
    rows = []
    try:
        async with _client(url, False) as mcp:
            for query in MENTION_QUERIES:
                result = await mcp.call_tool(tool, {"query": query.format(name=name), "source_types": ["slack"], "time_cutoff": cutoff})
                if result.is_error:
                    raise SourceError("The Slack search failed. Try again later.")
                payload = result.data if isinstance(result.data, dict) else result.structured_content or {}
                found = payload.get("results", []) if isinstance(payload, dict) else []
                if not isinstance(found, list):
                    raise SourceError("The Slack search server sent back something unexpected.")
                rows.extend(found)
    except SourceError:
        raise
    except connection_errors as error:
        sign_in = _sign_in_error(error)
        if sign_in:
            raise sign_in from error
        raise SourceError("The Slack search failed. If your sign-in expired, sign in again from Settings.") from error
    items = {item.key: item for item in (_item(row, mention) for row in rows) if item}
    return Batch(items=list(items.values()), detail="Public channel threads where someone asks you for something. DMs and private channels come from the Slack source.")


def _item(row: object, mention: re.Pattern[str]) -> Item | None:
    if not isinstance(row, dict):
        return None
    content = row.get("content") if isinstance(row.get("content"), str) else ""
    url = row.get("url") if isinstance(row.get("url"), str) else ""
    # A row holds the whole thread, so the ask must sit in the message that mentions you.
    line = next((line for line in content.splitlines() if mention.search(line) and ASK.search(line)), "")
    if not url.startswith("https://") or not line:
        return None
    opened = row.get("updated_at") if isinstance(row.get("updated_at"), str) else ""
    try:
        datetime.fromisoformat(opened.replace("Z", "+00:00"))
    except ValueError:
        opened = ""
    return Item(
        key="public_slack:" + hashlib.sha256(url.encode()).hexdigest()[:24],
        source="public_slack",
        title=short_title(line),
        url=url,
        opened_at=opened or None,
        reason="Mentioned you in a public channel",
        list_name="Asks",
        references=find_references(content),
    )
