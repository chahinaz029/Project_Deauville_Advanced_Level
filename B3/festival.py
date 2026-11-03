"""Festival objects and domain rules for the B3 implementation."""

import json
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "festival.json"
DAY_START_OFFSET = timedelta(hours=6)
MINIMUM_GAP = timedelta(minutes=30)


def slugify(text: str) -> str:
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


@dataclass(eq=False)
class Venue:
    name: str
    capacity: int
    address: str

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def to_view(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "capacity": self.capacity,
            "address": self.address,
        }


@dataclass(eq=False)
class Artist:
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
        return {
            "slug": self.slug,
            "name": self.name,
            "bio": self.bio,
            "photo_url": self.photo_url,
        }


@dataclass
class Performance:
    kind: str
    title: str
    venue: Venue
    start: datetime
    duration_minutes: int
    description: str = ""
    artist: Artist | None = None
    min_age: int = 0
    host: Artist | None = None
    acts: list[Artist] = field(default_factory=list)
    teacher: Artist | None = None
    max_participants: int = 0
    participants: list[str] = field(default_factory=list)

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.duration_minutes)

    @property
    def festival_day(self) -> date:
        return (self.start - DAY_START_OFFSET).date()

    @property
    def id(self) -> str:
        return f"{self.venue.slug}-{self.start:%Y-%m-%d-%H%M}"

    @property
    def artists(self) -> list[Artist]:
        if self.kind == "solo":
            return [self.artist] if self.artist else []
        if self.kind == "lineup":
            artists = [self.host] if self.host else []
            return artists + self.acts
        if self.kind == "workshop":
            return [self.teacher] if self.teacher else []
        return []

    @property
    def summary(self) -> str:
        if self.kind == "solo":
            return self.artist.name if self.artist else ""
        if self.kind == "lineup":
            host_name = self.host.name if self.host else ""
            act_names = ", ".join(artist.name for artist in self.acts)
            return f"hosted by {host_name}, with {act_names}"
        if self.kind == "workshop":
            teacher_name = self.teacher.name if self.teacher else ""
            return (
                f"with {teacher_name}, {len(self.participants)}/"
                f"{self.max_participants} places taken"
            )
        return ""

    @property
    def places_left(self) -> int:
        return max(0, self.max_participants - len(self.participants))

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
            "capacity": self.venue.capacity,
            "artists": [
                {"slug": artist.slug, "name": artist.name} for artist in self.artists
            ],
        }
        if self.kind == "solo":
            view.update(
                artist=self.artist.slug if self.artist else "",
                min_age=self.min_age,
            )
        elif self.kind == "lineup":
            view.update(
                host=self.host.slug if self.host else "",
                acts=[artist.slug for artist in self.acts],
            )
        elif self.kind == "workshop":
            view.update(
                teacher=self.teacher.slug if self.teacher else "",
                max_participants=self.max_participants,
                participants=self.participants.copy(),
                places_left=self.places_left,
            )
        return view

    def to_data(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "kind": self.kind,
            "title": self.title,
            "venue": self.venue.slug,
            "start": self.start.isoformat(timespec="minutes"),
            "duration_minutes": self.duration_minutes,
            "description": self.description,
        }
        if self.kind == "solo":
            row.update(
                artist=self.artist.slug if self.artist else "",
                min_age=self.min_age,
            )
        elif self.kind == "lineup":
            row.update(
                host=self.host.slug if self.host else "",
                acts=[artist.slug for artist in self.acts],
            )
        elif self.kind == "workshop":
            row.update(
                teacher=self.teacher.slug if self.teacher else "",
                max_participants=self.max_participants,
                participants=self.participants.copy(),
            )
        return row


@dataclass
class Festival:
    name: str
    first_day: date
    last_day: date
    venues: list[Venue]
    artists: list[Artist]
    performances: list[Performance]
    storage_path: Path | None = None

    @classmethod
    def from_data(
        cls, data: dict[str, Any], storage_path: Path | None = None
    ) -> "Festival":
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
                raise ValueError(f"Unknown venue '{slug}' in festival data.") from None

        def get_artist(slug: str) -> Artist:
            try:
                return artists_by_slug[slug]
            except KeyError:
                raise ValueError(f"Unknown artist '{slug}' in festival data.") from None

        performances = []
        for row in data["performances"]:
            kind = row["kind"]
            common: dict[str, Any] = {
                "kind": kind,
                "title": row["title"],
                "venue": get_venue(row["venue"]),
                "start": datetime.fromisoformat(row["start"]),
                "duration_minutes": row["duration_minutes"],
                "description": row.get("description", ""),
            }
            if kind == "solo":
                common.update(
                    artist=get_artist(row["artist"]),
                    min_age=row.get("min_age", 0),
                )
            elif kind == "lineup":
                common.update(
                    host=get_artist(row["host"]),
                    acts=[get_artist(slug) for slug in row.get("acts", [])],
                )
            elif kind == "workshop":
                common.update(
                    teacher=get_artist(row["teacher"]),
                    max_participants=row["max_participants"],
                    participants=row.get("participants", []).copy(),
                )
            else:
                raise ValueError(f"Unknown performance kind '{kind}'.")
            performances.append(Performance(**common))

        return cls(
            name=data["name"],
            first_day=date.fromisoformat(data["first_day"]),
            last_day=date.fromisoformat(data["last_day"]),
            venues=venues,
            artists=artists,
            performances=performances,
            storage_path=storage_path,
        )

    @classmethod
    def from_file(cls, path: Path) -> "Festival":
        try:
            with path.open(encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            raise ValueError(f"Data file '{path.name}' was not found.") from None
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Data file '{path.name}' is damaged (line {error.lineno})."
            ) from None
        try:
            return cls.from_data(data, storage_path=path)
        except (KeyError, TypeError) as error:
            raise ValueError(
                f"Data file '{path.name}' has an invalid structure."
            ) from error

    @property
    def days(self) -> list[date]:
        days = []
        current = self.first_day
        while current <= self.last_day:
            days.append(current)
            current += timedelta(days=1)
        return days

    def venue(self, slug: str) -> Venue:
        for venue in self.venues:
            if venue.slug == slug:
                return venue
        raise ValueError(f"No venue '{slug}'.")

    def artist(self, slug: str) -> Artist:
        for artist in self.artists:
            if artist.slug == slug:
                return artist
        raise ValueError(f"No artist '{slug}'.")

    def performance(self, performance_id: str) -> Performance:
        for performance in self.performances:
            if performance.id == performance_id:
                return performance
        raise ValueError(f"No performance '{performance_id}'.")

    def programme(
        self, day: date | None = None, venue: str | None = None
    ) -> list[Performance]:
        if day is not None and day not in self.days:
            raise ValueError(f"{day.isoformat()} is not a day of the festival.")
        if venue is not None:
            self.venue(venue)
        result = [
            performance
            for performance in self.performances
            if (day is None or performance.festival_day == day)
            and (venue is None or performance.venue.slug == venue)
        ]
        return sorted(result)

    def performances_of(self, artist: Artist | str) -> list[Performance]:
        if isinstance(artist, str):
            artist = self.artist(artist)
        return sorted(
            performance
            for performance in self.performances
            if performance.involves(artist)
        )

    def now_playing(self, at: datetime) -> list[Performance]:
        return sorted(
            performance
            for performance in self.performances
            if performance.is_running(at)
        )

    def up_next(self, at: datetime, limit: int = 3) -> list[Performance]:
        if limit < 0:
            raise ValueError("The number of upcoming performances cannot be negative.")
        return sorted(
            performance for performance in self.performances if performance.start > at
        )[:limit]

    def add(self, performance: Performance) -> None:
        if performance.kind != "solo":
            raise ValueError(
                "Only solo performances can be added from the command line."
            )
        if performance.venue not in self.venues:
            raise ValueError(f"No venue '{performance.venue.slug}'.")
        if performance.artist is None or performance.artist not in self.artists:
            raise ValueError("The solo performance needs a known artist.")
        if performance.start.tzinfo is not None:
            raise ValueError("Use a local start time without a time-zone offset.")
        if not 1 <= performance.duration_minutes <= 360:
            raise ValueError("Duration must be between 1 and 360 minutes.")
        if performance.festival_day not in self.days:
            raise ValueError(
                f"{performance.festival_day.isoformat()} is not a day of the festival."
            )

        new_end = performance.end
        for other in self.performances:
            other_start = other.start
            other_end = other.end
            too_close = (
                performance.start < other_end + MINIMUM_GAP
                and other_start < new_end + MINIMUM_GAP
            )
            if not too_close:
                continue
            if other.venue == performance.venue:
                raise ValueError(
                    f"{performance.venue.name} is busy with {other.title} "
                    f"({other_start:%Y-%m-%d %H:%M}-{other_end:%H:%M})."
                )
            if other.involves(performance.artist):
                raise ValueError(
                    f"{performance.artist.name} is on stage in {other.title}."
                )
        self.performances.append(performance)

    def cancel(self, performance_id: str) -> Performance:
        performance = self.performance(performance_id)
        self.performances.remove(performance)
        return performance

    def save(self) -> None:
        if self.storage_path is None:
            raise ValueError("No storage path is configured for this festival.")
        data = {
            "name": self.name,
            "first_day": self.first_day.isoformat(),
            "last_day": self.last_day.isoformat(),
            "venues": [
                {
                    "name": venue.name,
                    "capacity": venue.capacity,
                    "address": venue.address,
                }
                for venue in self.venues
            ],
            "artists": [
                {
                    "name": artist.name,
                    "bio": artist.bio,
                    "photo_url": artist.photo_url,
                }
                for artist in self.artists
            ],
            "performances": [
                performance.to_data() for performance in sorted(self.performances)
            ],
        }
        try:
            with self.storage_path.open("w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
        except OSError as error:
            raise ValueError(
                f"Could not save '{self.storage_path.name}': {error.strerror}."
            ) from None

    def festival_view(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "first_day": self.first_day.isoformat(),
            "last_day": self.last_day.isoformat(),
            "days": [day.isoformat() for day in self.days],
        }

    def artists_view(self) -> list[dict[str, str]]:
        return [
            artist.to_view()
            for artist in sorted(self.artists, key=lambda item: item.slug)
        ]

    def venues_view(self) -> list[dict[str, Any]]:
        return [venue.to_view() for venue in self.venues]
