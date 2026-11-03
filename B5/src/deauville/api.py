"""The HTTP API: reading for the website, writing for the admin.

create_app(storage) builds the application around a Storage it is handed;
it never opens a file itself."""

import threading
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from deauville.festival import (
    ADMIN_DIR,
    PUBLIC_DIR,
    Artist,
    ConflictError,
    DataFileError,
    Festival,
    FestivalError,
    InvalidError,
    Lineup,
    NotFoundError,
    Performance,
    SoloShow,
    Storage,
    Workshop,
    slugify,
)

STATUS_BY_ERROR: tuple[tuple[type[FestivalError], int], ...] = (
    (NotFoundError, 404),
    (ConflictError, 409),
    (InvalidError, 422),
    (DataFileError, 500),
)


# ---------- Request bodies: FastAPI answers 422 to any other shape ----------


class Body(BaseModel):
    """Base of every request body: an unknown field is refused."""

    model_config = ConfigDict(extra="forbid")


class PerformanceFields(Body):
    """The saved fields every performance body has (no id, end, summary...)."""

    title: str
    venue: str
    start: datetime
    duration_minutes: int
    description: str = ""


class SoloBody(PerformanceFields):
    """Body of a solo show."""

    kind: Literal["solo"]
    artist: str
    min_age: int = 0


class LineupBody(PerformanceFields):
    """Body of a lineup."""

    kind: Literal["lineup"]
    host: str
    acts: list[str]


class WorkshopBody(PerformanceFields):
    """Body of a workshop."""

    kind: Literal["workshop"]
    teacher: str
    max_participants: int
    # The admin page sends the current participants back on a PUT.
    # Left out, a PUT keeps the people already registered.
    participants: list[str] | None = None


AnyPerformanceBody = SoloBody | LineupBody | WorkshopBody

# The "kind" field decides which body is expected.
PerformanceBody = Annotated[AnyPerformanceBody, Field(discriminator="kind")]


class ParticipantBody(Body):
    """Body to register someone in a workshop."""

    name: str


class ArtistBody(Body):
    """Body to add an artist."""

    name: str
    bio: str = ""
    photo_url: str = ""


def build_performance(
    festival: Festival,
    body: AnyPerformanceBody,
    previous: Performance | None = None,
) -> Performance:
    """Turn a validated body into a domain object (names or slugs both work).

    `previous` is the performance being replaced (PUT), if any."""
    common = {
        "title": body.title.strip(),
        "venue": festival.venue(slugify(body.venue)),
        "start": body.start,
        "duration_minutes": body.duration_minutes,
        "description": body.description,
    }
    if isinstance(body, SoloBody):
        return SoloShow(
            **common,
            artist=festival.artist(slugify(body.artist)),
            min_age=body.min_age,
        )
    if isinstance(body, LineupBody):
        return Lineup(
            **common,
            host=festival.artist(slugify(body.host)),
            acts=tuple(festival.artist(slugify(name)) for name in body.acts),
        )
    if body.participants is not None:
        participants = tuple(body.participants)
    elif isinstance(previous, Workshop):
        participants = previous.participants
    else:
        participants = ()
    return Workshop(
        **common,
        teacher=festival.artist(slugify(body.teacher)),
        max_participants=body.max_participants,
        participants=participants,
    )


def create_app(
    storage: Storage,
    public_dir: Path = PUBLIC_DIR,
    admin_dir: Path = ADMIN_DIR,
) -> FastAPI:
    """Build the application around a storage (the real file, or a test's copy)."""
    app = FastAPI(title="Festival API")

    # Routes run in a thread pool: one writer at a time (read, change, save).
    write_lock = threading.Lock()

    # One handler turns the error family into statuses: routes never use try.
    @app.exception_handler(FestivalError)
    async def festival_error_handler(
        request: Request, error: FestivalError
    ) -> JSONResponse:
        status = next(
            (code for kind, code in STATUS_BY_ERROR if isinstance(error, kind)), 400
        )
        return JSONResponse(status_code=status, content={"detail": str(error)})

    # ---------- Reading ----------

    @app.get("/api/festival")
    def get_festival() -> dict:
        return storage.load().festival_view()

    @app.get("/api/venues")
    def list_venues() -> list[dict]:
        return storage.load().venues_view()

    @app.get("/api/artists")
    def list_artists() -> list[dict]:
        return storage.load().artists_view()

    @app.get("/api/artists/{slug}")
    def get_artist(slug: str) -> dict:
        festival = storage.load()
        artist = festival.artist(slug)
        view = artist.to_view()
        view["performances"] = [
            performance.to_view() for performance in festival.performances_of(artist)
        ]
        return view

    @app.get("/api/programme")
    def get_programme(day: date | None = None, venue: str | None = None) -> list[dict]:
        festival = storage.load()
        return [
            performance.to_view()
            for performance in festival.programme(day=day, venue=venue)
        ]

    @app.get("/api/performances/{performance_id}")
    def get_performance(performance_id: str) -> dict:
        return storage.load().performance(performance_id).to_view()

    @app.get("/api/now")
    def get_now(at: datetime | None = None) -> dict:
        festival = storage.load()
        moment = at if at is not None else datetime.now()
        if moment.tzinfo is not None:
            moment = moment.replace(tzinfo=None)
        return {
            "at": moment.isoformat(timespec="minutes"),
            "now_playing": [p.to_view() for p in festival.now_playing(moment)],
            "up_next": [p.to_view() for p in festival.up_next(moment, limit=3)],
        }

    # ---------- Writing (admin) ----------

    @app.post("/api/performances", status_code=201)
    def create_performance(body: PerformanceBody) -> dict:
        with write_lock:
            festival = storage.load()
            performance = festival.add(build_performance(festival, body))
            storage.save(festival)
        return performance.to_view()

    @app.put("/api/performances/{performance_id}")
    def replace_performance(performance_id: str, body: PerformanceBody) -> dict:
        with write_lock:
            festival = storage.load()
            previous = festival.performance(performance_id)
            performance = festival.update(
                performance_id, build_performance(festival, body, previous)
            )
            storage.save(festival)
        return performance.to_view()

    @app.delete("/api/performances/{performance_id}", status_code=204)
    def cancel_performance(performance_id: str) -> None:
        with write_lock:
            festival = storage.load()
            festival.cancel(performance_id)
            storage.save(festival)

    @app.post("/api/performances/{performance_id}/participants", status_code=201)
    def register_participant(performance_id: str, body: ParticipantBody) -> dict:
        with write_lock:
            festival = storage.load()
            workshop = festival.register(performance_id, body.name)
            storage.save(festival)
        return workshop.to_view()

    @app.post("/api/artists", status_code=201)
    def create_artist(body: ArtistBody) -> dict:
        with write_lock:
            festival = storage.load()
            artist = festival.add_artist(
                Artist(name=body.name, bio=body.bio, photo_url=body.photo_url)
            )
            storage.save(festival)
        return artist.to_view()

    # Always after the routes. /admin before /, or the site swallows it.
    app.mount("/admin", StaticFiles(directory=admin_dir, html=True), name="admin")
    app.mount("/", StaticFiles(directory=public_dir, html=True), name="web")
    return app
