"""Local web view and same-origin mutations."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from worktray.briefs import MeetingBrief, StandupNote, meeting_brief, standup_note
from worktray.engine import Engine, create_engine
from worktray.models import Item, ItemEdit
from worktray import APP_NAME
from worktray.paths import database
from worktray.sources.cleanup import apply_suggestion, reject_suggestion
from worktray.store import Store
from worktray.web.settings import settings_router


STATIC = Path(__file__).resolve().parent / "static"


class NewItem(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    key: str = Field(default_factory=lambda: str(uuid4()), max_length=100)
    note: str = Field(default="", max_length=2000)
    list_name: str = Field(default="", max_length=60)


class EditRequest(ItemEdit):
    key: str


class RefreshRequest(BaseModel):
    sources: list[str] | None = None


class SettingsRequest(BaseModel):
    team_jql: str = Field(min_length=1, max_length=1000)


class IntervalRequest(BaseModel):
    source: str
    seconds: int | None


class AutoRefreshRequest(BaseModel):
    enabled: bool


class SuggestionDecision(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    accept: bool


class TeamExclusionRequest(BaseModel):
    owner_id: str = Field(min_length=1, max_length=240)
    name: str = Field(default="", max_length=240)
    excluded: bool


def create_app(store: Store | None = None, engine: Engine | None = None) -> FastAPI:
    """Restore saved work for this local process."""
    store = store if store is not None else Store(database())
    engine = engine if engine is not None else create_engine(store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        schedule = asyncio.create_task(engine.run_schedule())
        yield
        schedule.cancel()
        await asyncio.gather(schedule, return_exceptions=True)
        for task in engine.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*engine.tasks.values(), return_exceptions=True)

    app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.engine = engine
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

    @app.middleware("http")
    async def protect(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            expected = f"{request.url.scheme}://{request.headers.get('host')}"
            if request.headers.get("origin") != expected:
                return JSONResponse({"detail": "Same-origin request required"}, status_code=403)
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        return response

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/state")
    async def state() -> dict:
        return engine.snapshot()

    @app.get("/api/standup")
    async def standup() -> StandupNote:
        return standup_note([item for item in engine.items() if item.personal])

    @app.get("/api/brief")
    async def brief(key: str) -> MeetingBrief:
        items = [item for item in engine.items() if item.personal]
        event = next((item for item in items if item.key == key and item.source == "calendar"), None)
        if event is None:
            raise HTTPException(404, "Meeting is not in the current view")
        return meeting_brief(event, items)

    @app.post("/api/refresh", status_code=202)
    async def refresh(body: RefreshRequest) -> dict:
        try:
            return {"started": engine.start(body.sources)}
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.post("/api/items")
    async def add(body: NewItem) -> dict:
        item = Item(key=f"manual:{body.key}", title=body.title, source="manual", status="open", note=body.note, list_name=body.list_name)
        store.ingest([item])
        return {"key": item.key}

    @app.patch("/api/items")
    async def edit(body: EditRequest) -> dict:
        patch = ItemEdit.model_validate(body.model_dump(exclude={"key"}, exclude_none=True))
        live_keys = {item.key for batch in engine.live.values() for item in batch}
        try:
            if body.key in live_keys:
                store.annotate(body.key, patch)
            else:
                store.edit(body.key, patch)
        except KeyError as error:
            raise HTTPException(404, "Item is not in the current view") from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        return {"ok": True}

    @app.post("/api/suggestions")
    async def decide(body: SuggestionDecision) -> dict:
        try:
            if body.accept:
                apply_suggestion(store, body.id)
            else:
                reject_suggestion(store, body.id)
        except KeyError as error:
            raise HTTPException(404, "Suggestion is no longer pending") from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        return {"ok": True}

    @app.post("/api/settings")
    async def settings(body: SettingsRequest) -> dict:
        store.save_setting("team_jql", body.team_jql)
        store.save_setting("team_scope_origin", "Set by you")
        # With Jira off, the scope is kept for later rather than failing the save.
        started = engine.start(["jira"]) if "jira" in engine.active() else []
        return {"ok": True, "started": started}

    @app.post("/api/settings/refresh-interval")
    async def refresh_interval(body: IntervalRequest) -> dict:
        try:
            engine.set_interval(body.source, body.seconds)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        return {"ok": True}

    @app.post("/api/settings/auto-refresh")
    async def auto_refresh(body: AutoRefreshRequest) -> dict:
        engine.set_auto_refresh(body.enabled)
        return {"ok": True}

    @app.post("/api/team/exclusions")
    async def team_exclusion(body: TeamExclusionRequest) -> dict:
        try:
            engine.set_team_exclusion(body.owner_id, body.excluded)
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        return {"ok": True}

    app.include_router(settings_router(store, engine))
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
