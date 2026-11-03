from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from festival import DATA_FILE, Festival

WEB_DIR = Path(__file__).resolve().parent.parent / "web" / "public"

app = FastAPI(title="Festival API")


def load_festival() -> Festival:
    """Relit le fichier à chaque requête (500 s'il est illisible)."""
    try:
        return Festival.from_file(DATA_FILE)
    except ValueError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/api/festival")
def get_festival() -> dict:
    return load_festival().festival_view()


@app.get("/api/venues")
def list_venues() -> list[dict]:
    return load_festival().venues_view()


@app.get("/api/artists")
def list_artists() -> list[dict]:
    return load_festival().artists_view()


@app.get("/api/artists/{slug}")
def get_artist(slug: str) -> dict:
    festival = load_festival()
    try:
        artist = festival.artist(slug)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    view = artist.to_view()
    view["performances"] = [
        performance.to_view() for performance in festival.performances_of(artist)
    ]
    return view


@app.get("/api/programme")
def get_programme(day: date | None = None, venue: str | None = None) -> list[dict]:
    festival = load_festival()
    if day is not None and day not in festival.days:
        raise HTTPException(
            status_code=422,
            detail=f"{day.isoformat()} is not a day of the festival.",
        )
    try:
        performances = festival.programme(day=day, venue=venue)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    return [performance.to_view() for performance in performances]


@app.get("/api/performances/{performance_id}")
def get_performance(performance_id: str) -> dict:
    festival = load_festival()
    try:
        return festival.performance(performance_id).to_view()
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None


@app.get("/api/now")
def get_now(at: datetime | None = None) -> dict:
    festival = load_festival()
    moment = at if at is not None else datetime.now()
    if moment.tzinfo is not None:
        moment = moment.replace(tzinfo=None)
    return {
        "at": moment.isoformat(timespec="minutes"),
        "now_playing": [p.to_view() for p in festival.now_playing(moment)],
        "up_next": [p.to_view() for p in festival.up_next(moment, limit=3)],
    }


# Toujours après les routes.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
