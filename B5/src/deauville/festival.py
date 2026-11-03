"""The festival: errors, things on the programme, the Festival and its storage.

Everything that is not the API (api.py) or the command line (main.py)."""

import copy
import dataclasses
import json
import os
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

DAY_START_OFFSET = timedelta(hours=6)
MINIMUM_GAP = timedelta(minutes=30)
ACT_MINUTES = 10
HOST_MINUTES = 3


# ---------- Our own errors: one family, the type says what went wrong ----------


class FestivalError(Exception):
    """Every error the festival raises on purpose. Catch this to catch them all."""


class NotFoundError(FestivalError):
    """The venue, artist or performance does not exist."""


class ConflictError(FestivalError):
    """The request is fine, but the festival's current state forbids it."""


class InvalidError(FestivalError):
    """A value breaks a rule, whatever the state of the festival."""


class DataFileError(FestivalError):
    """The data file is missing, damaged or inconsistent."""


# ---------- Venues, artists and the three kinds of performances ----------


def slugify(text: str) -> str:
    """Turn a name into a slug: "Élodie Marchal" becomes "elodie-marchal"."""
    plain = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    result = ""
    for character in plain:
        if character.isalnum():
            result += character
        elif result and not result.endswith("-"):
            result += "-"
    return result.rstrip("-")


@dataclass(eq=False, frozen=True)
class Venue:
    """A place where performances happen. The slug comes from the name."""

    name: str
    capacity: int
    address: str

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def to_view(self) -> dict[str, Any]:
        """The venue as the API shows it."""
        return {
            "slug": self.slug,
            "name": self.name,
            "capacity": self.capacity,
            "address": self.address,
        }


@dataclass(eq=False, frozen=True)
class Artist:
    """Someone who performs. Two artists with the same slug are the same artist."""

    name: str
    bio: str = ""
    photo_url: str = ""

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Artist):
            return NotImplemented
        return self.slug == other.slug

    def __hash__(self) -> int:
        return hash(self.slug)

    def to_view(self) -> dict[str, str]:
        """The artist as the API shows it."""
        return {
            "slug": self.slug,
            "name": self.name,
            "bio": self.bio,
            "photo_url": self.photo_url,
        }


# ---------- Performances : immuables, une famille de trois classes ----------
# A performance never changes after it is built. To "modify" one, the festival
# builds a new one, checks the rules, and only then swaps it in.


@dataclass(kw_only=True, frozen=True)
class Performance(ABC):
    """What every performance has in common. Cannot be created directly:
    use SoloShow, Lineup or Workshop."""

    kind: ClassVar[str]

    title: str
    venue: Venue
    start: datetime
    duration_minutes: int
    description: str = ""

    # ----- commun à tous les types -----

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.duration_minutes)

    @property
    def festival_day(self) -> date:
        """The day of the festival it belongs to: a day ends at 06:00."""
        return (self.start - DAY_START_OFFSET).date()

    @property
    def id(self) -> str:
        return f"{self.venue.slug}-{self.start:%Y-%m-%d-%H%M}"

    @property
    def capacity(self) -> int:
        return self.venue.capacity

    def involves(self, artist: Artist) -> bool:
        return artist in self.artists

    def is_running(self, at: datetime) -> bool:
        return self.start <= at < self.end

    def __lt__(self, other: "Performance") -> bool:
        return (self.start, self.venue.name) < (other.start, other.venue.name)

    def __str__(self) -> str:
        return (
            f"{self.festival_day:%Y-%m-%d} {self.start:%H:%M}-{self.end:%H:%M} | "
            f"{self.venue.name} | {self.title} ({self.kind})"
        )

    def to_view(self) -> dict[str, Any]:
        """The performance as the API shows it (common fields + its kind's)."""
        view: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "venue": self.venue.slug,
            "venue_name": self.venue.name,
            "start": self.start.isoformat(timespec="minutes"),
            "end": self.end.isoformat(timespec="minutes"),
            "duration_minutes": self.duration_minutes,
            "festival_day": self.festival_day.isoformat(),
            "description": self.description,
            "summary": self.summary,
            "capacity": self.capacity,
            "artists": [
                {"slug": artist.slug, "name": artist.name} for artist in self.artists
            ],
        }
        view.update(self._view_fields())
        return view

    def to_data(self) -> dict[str, Any]:
        """The performance as the data file stores it (saved fields only)."""
        row: dict[str, Any] = {
            "kind": self.kind,
            "title": self.title,
            "venue": self.venue.slug,
            "start": self.start.isoformat(timespec="minutes"),
            "duration_minutes": self.duration_minutes,
            "description": self.description,
        }
        row.update(self._data_fields())
        return row

    @classmethod
    def from_row(
        cls,
        row: dict[str, Any],
        get_venue: Callable[[str], Venue],
        get_artist: Callable[[str], Artist],
    ) -> "Performance":
        """Build a performance of this class from a row of the data file."""
        return cls(
            title=row["title"],
            venue=get_venue(row["venue"]),
            start=datetime.fromisoformat(row["start"]),
            duration_minutes=row["duration_minutes"],
            description=row.get("description", ""),
            **cls._fields_from_row(row, get_artist),
        )

    # ----- propre à chaque type -----

    @property
    @abstractmethod
    def artists(self) -> list[Artist]:
        """Everyone on stage, in order of appearance."""

    @property
    @abstractmethod
    def summary(self) -> str:
        """One line for the programme."""

    @abstractmethod
    def _view_fields(self) -> dict[str, Any]:
        """Fields added to the API view."""

    @abstractmethod
    def _data_fields(self) -> dict[str, Any]:
        """Fields added to the data file."""

    @classmethod
    @abstractmethod
    def _fields_from_row(
        cls, row: dict[str, Any], get_artist: Callable[[str], Artist]
    ) -> dict[str, Any]:
        """Constructor arguments that are specific to this kind."""


@dataclass(kw_only=True, frozen=True)
class SoloShow(Performance):
    """One artist on stage, with a minimum age (0 to 18)."""

    kind: ClassVar[str] = "solo"

    artist: Artist
    min_age: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.min_age <= 18:
            raise InvalidError("The minimum age must be between 0 and 18.")

    @property
    def artists(self) -> list[Artist]:
        return [self.artist]

    @property
    def summary(self) -> str:
        return self.artist.name

    def _view_fields(self) -> dict[str, Any]:
        return {"artist": self.artist.slug, "min_age": self.min_age}

    def _data_fields(self) -> dict[str, Any]:
        return {"artist": self.artist.slug, "min_age": self.min_age}

    @classmethod
    def _fields_from_row(
        cls, row: dict[str, Any], get_artist: Callable[[str], Artist]
    ) -> dict[str, Any]:
        return {
            "artist": get_artist(row["artist"]),
            "min_age": row.get("min_age", 0),
        }


@dataclass(kw_only=True, frozen=True)
class Lineup(Performance):
    """A host introducing at least two acts, each of whom appears once."""

    kind: ClassVar[str] = "lineup"

    host: Artist
    acts: tuple[Artist, ...] = ()

    @staticmethod
    def minimum_duration(act_count: int) -> int:
        """10 minutes per act, 3 for the host between two acts."""
        return ACT_MINUTES * act_count + HOST_MINUTES * max(0, act_count - 1)

    def __post_init__(self) -> None:
        object.__setattr__(self, "acts", tuple(self.acts))
        if len(self.acts) < 2:
            raise InvalidError("A lineup needs at least 2 acts.")
        if len(set(self.acts)) != len(self.acts):
            raise InvalidError("Each act can appear only once in a lineup.")
        if self.host in self.acts:
            raise InvalidError("The host of a lineup cannot also be one of its acts.")
        needed = self.minimum_duration(len(self.acts))
        if self.duration_minutes < needed:
            raise InvalidError(
                f"A lineup of {len(self.acts)} acts needs at least {needed} minutes."
            )

    @property
    def artists(self) -> list[Artist]:
        return [self.host, *self.acts]

    @property
    def summary(self) -> str:
        act_names = ", ".join(artist.name for artist in self.acts)
        return f"hosted by {self.host.name}, with {act_names}"

    def _view_fields(self) -> dict[str, Any]:
        return {
            "host": self.host.slug,
            "acts": [artist.slug for artist in self.acts],
        }

    def _data_fields(self) -> dict[str, Any]:
        return self._view_fields()

    @classmethod
    def _fields_from_row(
        cls, row: dict[str, Any], get_artist: Callable[[str], Artist]
    ) -> dict[str, Any]:
        return {
            "host": get_artist(row["host"]),
            "acts": tuple(get_artist(slug) for slug in row.get("acts", [])),
        }


@dataclass(kw_only=True, frozen=True)
class Workshop(Performance):
    """A teacher and a limited number of participants (known by their names)."""

    kind: ClassVar[str] = "workshop"

    teacher: Artist
    max_participants: int
    participants: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "participants", tuple(self.participants))
        if self.max_participants < 1:
            raise InvalidError("A workshop needs at least 1 place.")
        if len({slugify(name) for name in self.participants}) != len(self.participants):
            raise InvalidError("Each participant can be registered only once.")
        if len(self.participants) > self.places:
            raise InvalidError(
                f"{len(self.participants)} participants do not fit in "
                f"{self.places} places."
            )

    @property
    def places(self) -> int:
        """The places really available: never more than the venue's seats."""
        return min(self.max_participants, self.venue.capacity)

    @property
    def capacity(self) -> int:
        return self.places

    @property
    def places_left(self) -> int:
        return max(0, self.places - len(self.participants))

    @property
    def artists(self) -> list[Artist]:
        return [self.teacher]

    @property
    def summary(self) -> str:
        return (
            f"with {self.teacher.name}, {len(self.participants)}/"
            f"{self.places} places taken"
        )

    def with_participant(self, name: str) -> "Workshop":
        """A new workshop with one more participant, or an error."""
        name = " ".join(name.split())
        key = slugify(name)
        if not key:
            raise InvalidError("A participant needs a name.")
        if any(slugify(known) == key for known in self.participants):
            raise ConflictError(f"{name} is already registered for {self.title}.")
        if self.places_left == 0:
            raise ConflictError(f"{self.title} is full.")
        return dataclasses.replace(self, participants=(*self.participants, name))

    def _view_fields(self) -> dict[str, Any]:
        return {
            "teacher": self.teacher.slug,
            "max_participants": self.max_participants,
            "participants": list(self.participants),
            "places_left": self.places_left,
        }

    def _data_fields(self) -> dict[str, Any]:
        return {
            "teacher": self.teacher.slug,
            "max_participants": self.max_participants,
            "participants": list(self.participants),
        }

    @classmethod
    def _fields_from_row(
        cls, row: dict[str, Any], get_artist: Callable[[str], Artist]
    ) -> dict[str, Any]:
        return {
            "teacher": get_artist(row["teacher"]),
            "max_participants": row["max_participants"],
            "participants": tuple(row.get("participants", [])),
        }


# Le seul endroit où le "kind" du fichier choisit une classe.
PERFORMANCE_CLASSES: dict[str, type[Performance]] = {
    cls.kind: cls for cls in (SoloShow, Lineup, Workshop)
}


# ---------- The festival: it does not know where it is stored ----------


class Festival:
    """The festival. Its collections are private: read through the properties
    (which return copies), change through the methods (which check the rules)."""

    def __init__(
        self,
        name: str,
        first_day: date,
        last_day: date,
        venues: list[Venue],
        artists: list[Artist],
        performances: list[Performance],
    ) -> None:
        self.name = name
        self.first_day = first_day
        self.last_day = last_day
        self._venues = list(venues)
        self._artists = list(artists)
        self._performances = list(performances)

    # ----- lecture : toujours des copies -----

    @property
    def venues(self) -> tuple[Venue, ...]:
        return tuple(self._venues)

    @property
    def artists(self) -> tuple[Artist, ...]:
        return tuple(self._artists)

    @property
    def performances(self) -> tuple[Performance, ...]:
        return tuple(self._performances)

    @property
    def days(self) -> list[date]:
        """Every day from the first to the last, both included."""
        days = []
        current = self.first_day
        while current <= self.last_day:
            days.append(current)
            current += timedelta(days=1)
        return days

    # ----- chargement -----

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "Festival":
        """Build a festival from plain data (what a storage hands over)."""
        try:
            return cls._build(data)
        except DataFileError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise DataFileError(
                "The festival data has an invalid structure."
            ) from error
        except FestivalError as error:
            raise DataFileError(f"The festival data breaks a rule: {error}") from error

    @classmethod
    def _build(cls, data: dict[str, Any]) -> "Festival":
        venues = [Venue(**row) for row in data["venues"]]
        artists = [
            Artist(
                name=row["name"],
                bio=row.get("bio", ""),
                photo_url=row.get("photo_url", ""),
            )
            for row in data["artists"]
        ]
        venues_by_slug = {venue.slug: venue for venue in venues}
        artists_by_slug = {artist.slug: artist for artist in artists}

        def get_venue(slug: str) -> Venue:
            try:
                return venues_by_slug[slug]
            except KeyError:
                raise DataFileError(
                    f"Unknown venue '{slug}' in festival data."
                ) from None

        def get_artist(slug: str) -> Artist:
            try:
                return artists_by_slug[slug]
            except KeyError:
                raise DataFileError(
                    f"Unknown artist '{slug}' in festival data."
                ) from None

        performances = []
        for row in data["performances"]:
            kind = row["kind"]
            performance_class = PERFORMANCE_CLASSES.get(kind)
            if performance_class is None:
                raise DataFileError(f"Unknown performance kind '{kind}'.")
            performances.append(performance_class.from_row(row, get_venue, get_artist))

        return cls(
            name=data["name"],
            first_day=date.fromisoformat(data["first_day"]),
            last_day=date.fromisoformat(data["last_day"]),
            venues=venues,
            artists=artists,
            performances=performances,
        )

    def to_data(self) -> dict[str, Any]:
        """Plain data, ready for any storage (JSON file, memory, ...)."""
        return {
            "name": self.name,
            "first_day": self.first_day.isoformat(),
            "last_day": self.last_day.isoformat(),
            "venues": [
                {"name": v.name, "capacity": v.capacity, "address": v.address}
                for v in self._venues
            ],
            "artists": [
                {"name": a.name, "bio": a.bio, "photo_url": a.photo_url}
                for a in self._artists
            ],
            "performances": [p.to_data() for p in sorted(self._performances)],
        }

    # ----- recherche -----

    def venue(self, slug: str) -> Venue:
        """The venue with this slug, or NotFoundError."""
        for venue in self._venues:
            if venue.slug == slug:
                return venue
        raise NotFoundError(f"No venue '{slug}'.")

    def artist(self, slug: str) -> Artist:
        """The artist with this slug, or NotFoundError."""
        for artist in self._artists:
            if artist.slug == slug:
                return artist
        raise NotFoundError(f"No artist '{slug}'.")

    def performance(self, performance_id: str) -> Performance:
        """The performance with this id, or NotFoundError."""
        for performance in self._performances:
            if performance.id == performance_id:
                return performance
        raise NotFoundError(f"No performance '{performance_id}'.")

    def programme(
        self, day: date | None = None, venue: str | None = None
    ) -> list[Performance]:
        """The performances in programme order, optionally of one day and/or venue."""
        if day is not None and day not in self.days:
            raise InvalidError(f"{day.isoformat()} is not a day of the festival.")
        if venue is not None:
            self.venue(venue)
        result = [
            performance
            for performance in self._performances
            if (day is None or performance.festival_day == day)
            and (venue is None or performance.venue.slug == venue)
        ]
        return sorted(result)

    def performances_of(self, artist: Artist | str) -> list[Performance]:
        """Every performance an artist takes part in, in programme order."""
        if isinstance(artist, str):
            artist = self.artist(artist)
        return sorted(
            performance
            for performance in self._performances
            if performance.involves(artist)
        )

    def now_playing(self, at: datetime) -> list[Performance]:
        """What is on stage at this moment."""
        return sorted(
            performance
            for performance in self._performances
            if performance.is_running(at)
        )

    def up_next(self, at: datetime, limit: int = 3) -> list[Performance]:
        """The next performances to start after this moment (3 by default)."""
        if limit < 0:
            raise InvalidError(
                "The number of upcoming performances cannot be negative."
            )
        return sorted(
            performance for performance in self._performances if performance.start > at
        )[:limit]

    # ----- écriture : les seules portes, toutes derrière les règles -----

    def _check_schedulable(
        self, performance: Performance, ignoring: Performance | None = None
    ) -> None:
        """Every rule for a performance on the programme. Raises, never changes.

        `ignoring` is the performance being replaced: it must not clash with
        its own new version."""
        if not performance.title.strip():
            raise InvalidError("A performance needs a title.")
        if performance.venue not in self._venues:
            raise NotFoundError(f"No venue '{performance.venue.slug}'.")
        for artist in performance.artists:
            if artist not in self._artists:
                raise NotFoundError(f"No artist '{artist.slug}'.")
        if performance.start.tzinfo is not None:
            raise InvalidError("Use a local start time without a time-zone offset.")
        if not 1 <= performance.duration_minutes <= 360:
            raise InvalidError("Duration must be between 1 and 360 minutes.")
        if performance.festival_day not in self.days:
            # API.md lists "date outside the festival" among the 409.
            raise ConflictError(
                f"{performance.festival_day.isoformat()} is not a day of the festival."
            )

        new_end = performance.end
        for other in self._performances:
            if other is ignoring:
                continue
            too_close = (
                performance.start < other.end + MINIMUM_GAP
                and other.start < new_end + MINIMUM_GAP
            )
            if not too_close:
                continue
            if other.venue == performance.venue:
                raise ConflictError(
                    f"{performance.venue.name} is busy with {other.title} "
                    f"({other.start:%Y-%m-%d %H:%M}-{other.end:%H:%M})."
                )
            for artist in performance.artists:
                if other.involves(artist):
                    raise ConflictError(f"{artist.name} is on stage in {other.title}.")

    def add(self, performance: Performance) -> Performance:
        """Put a performance on the programme, if every rule allows it."""
        self._check_schedulable(performance)
        self._performances.append(performance)
        return performance

    def update(self, performance_id: str, new: Performance) -> Performance:
        """Replace a performance by another one. All or nothing."""
        old = self.performance(performance_id)
        if (
            isinstance(old, Workshop)
            and old.participants
            and not isinstance(new, Workshop)
        ):
            raise ConflictError(
                f"{old.title} has participants and must stay a workshop."
            )
        self._check_schedulable(new, ignoring=old)
        self._swap(old, new)
        return new

    def cancel(self, performance_id: str) -> Performance:
        """Remove a performance from the programme and return it."""
        performance = self.performance(performance_id)
        self._performances = [p for p in self._performances if p is not performance]
        return performance

    def register(self, performance_id: str, name: str) -> Workshop:
        """Register a participant in a workshop, if there is room."""
        old = self.performance(performance_id)
        if not isinstance(old, Workshop):
            raise InvalidError(f"{old.title} is not a workshop.")
        new = old.with_participant(name)
        self._swap(old, new)
        return new

    def add_artist(self, artist: Artist) -> Artist:
        """Add an artist; "Zoé Tanguy" and "zoe tanguy" are the same artist."""
        name = " ".join(artist.name.split())
        if not slugify(name):
            raise InvalidError("An artist needs a name.")
        artist = dataclasses.replace(artist, name=name)
        if artist in self._artists:
            raise ConflictError(f"The artist '{name}' already exists.")
        self._artists.append(artist)
        return artist

    def _swap(self, old: Performance, new: Performance) -> None:
        self._performances = [new if p is old else p for p in self._performances]

    # ----- vues -----

    def festival_view(self) -> dict[str, Any]:
        """The festival as the API shows it."""
        return {
            "name": self.name,
            "first_day": self.first_day.isoformat(),
            "last_day": self.last_day.isoformat(),
            "days": [day.isoformat() for day in self.days],
        }

    def artists_view(self) -> list[dict[str, str]]:
        """Every artist as the API shows them, in alphabetical order."""
        return [
            artist.to_view()
            for artist in sorted(self._artists, key=lambda item: item.slug)
        ]

    def venues_view(self) -> list[dict[str, Any]]:
        """Every venue as the API shows it, in the order they were added."""
        return [venue.to_view() for venue in self._venues]


# ---------- Storage: an interface, and two parts that fit it ----------


class Storage(ABC):
    """Anything that can hand over a festival and take it back."""

    @abstractmethod
    def load(self) -> Festival:
        """A fresh festival, built from what is stored."""

    @abstractmethod
    def save(self, festival: Festival) -> None:
        """Keep this festival; the next load() returns it."""


class JsonStorage(Storage):
    """The festival in a JSON file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> Festival:
        name = self.path.name
        try:
            with self.path.open(encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            raise DataFileError(f"Data file '{name}' was not found.") from None
        except json.JSONDecodeError as error:
            raise DataFileError(
                f"Data file '{name}' is damaged (line {error.lineno})."
            ) from None
        except OSError as error:
            raise DataFileError(f"Could not read '{name}': {error.strerror}.") from None
        try:
            return Festival.from_data(data)
        except DataFileError as error:
            raise DataFileError(f"Data file '{name}': {error}") from error

    def save(self, festival: Festival) -> None:
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            # Write beside the file, then swap: a crash never leaves half a file.
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(festival.to_data(), file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temporary, self.path)
        except OSError as error:
            raise DataFileError(
                f"Could not save '{self.path.name}': {error.strerror}."
            ) from None


class MemoryStorage(Storage):
    """The festival in memory: handy for tests, nothing touches the disk.

    It keeps plain data and builds a new Festival on every load(), exactly
    like the file does, so both storages behave the same."""

    def __init__(self, data: dict[str, Any] | Festival) -> None:
        if isinstance(data, Festival):
            data = data.to_data()
        self._data = copy.deepcopy(data)

    def load(self) -> Festival:
        return Festival.from_data(copy.deepcopy(self._data))

    def save(self, festival: Festival) -> None:
        self._data = festival.to_data()


# ---------- Where the data and the website are ----------


def project_root() -> Path:
    """The first folder above this file that holds a pyproject.toml."""
    for folder in Path(__file__).resolve().parents:
        if (folder / "pyproject.toml").is_file():
            return folder
    # Installed somewhere without a project around it: work from the current folder.
    return Path.cwd()


ROOT = project_root()
DATA_FILE = ROOT / "data" / "festival.json"
PUBLIC_DIR = ROOT / "web" / "public"
ADMIN_DIR = ROOT / "web" / "admin"
