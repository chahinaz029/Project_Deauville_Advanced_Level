import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "festival.json"
BREAK_MINUTES = 30


# ---------- Lecture et écriture des données ----------


def read_festival():
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON data: {error}") from error
    except OSError as error:
        raise ValueError(f"Cannot read festival data: {error}") from error

    if not isinstance(data, dict):
        raise ValueError("Festival data must be a JSON object.")

    for key in ("venues", "artists", "performances"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"Invalid or missing '{key}' list in festival data.")

    return data


def save_festival(data):
    try:
        with DATA_FILE.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
    except OSError as error:
        raise ValueError(f"Cannot save festival data: {error}") from error


# ---------- Recherche et identifiants ----------


def slugify(name):
    name = unicodedata.normalize("NFKD", name)
    name = "".join(
        character for character in name if not unicodedata.combining(character)
    )
    name = name.lower()
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def find_venue(data, slug):
    for venue in data["venues"]:
        if slugify(venue["name"]) == slug:
            return venue
    return None


def find_artist(data, slug):
    for artist in data["artists"]:
        if slugify(artist["name"]) == slug:
            return artist
    return None


def venue_name(data, slug):
    venue = find_venue(data, slug)
    return venue["name"] if venue else slug


def artist_name(data, slug):
    artist = find_artist(data, slug)
    return artist["name"] if artist else slug


def performance_start(performance):
    return datetime.fromisoformat(performance["start"])


def performance_end(performance):
    duration = int(performance["duration_minutes"])
    return performance_start(performance) + timedelta(minutes=duration)


def festival_day(performance):
    return (performance_start(performance) - timedelta(hours=6)).date()


def performance_id(performance):
    start = performance_start(performance)
    return f"{performance['venue']}-{start:%Y-%m-%d-%H%M}"


def time_range(performance):
    start = performance_start(performance)
    end = performance_end(performance)
    return f"{start:%H:%M}-{end:%H:%M}"


# ---------- Artistes participant à une prestation ----------


def performance_artists(performance):
    """Retourne tous les artistes, quel que soit leur rôle."""
    artists = []

    for key in ("artist", "host", "teacher"):
        slug = performance.get(key)
        if slug:
            artists.append(slug)

    artists.extend(performance.get("acts", []))
    return set(artists)


def performance_kind(performance):
    return performance.get("kind", "unknown")


# ---------- Affichage ----------


def show_summary(data):
    print(data["name"])
    print(f"Venues: {len(data['venues'])}")
    print(f"Artists: {len(data['artists'])}")
    print(f"Performances: {len(data['performances'])}")


def show_venues(data):
    for venue in data["venues"]:
        print(f"{slugify(venue['name'])} | {venue['name']} ({venue['capacity']} seats)")


def show_programme(data, day_text):
    try:
        day = date.fromisoformat(day_text)
    except ValueError:
        raise ValueError(f"'{day_text}' is not a day, use YYYY-MM-DD.") from None

    first_day = date.fromisoformat(data["first_day"])
    last_day = date.fromisoformat(data["last_day"])

    if not first_day <= day <= last_day:
        raise ValueError(f"{day} is not a day of the festival.")

    print(f"Programme for {day:%A %d %B}:")

    performances = [
        performance
        for performance in data["performances"]
        if festival_day(performance) == day
    ]
    performances.sort(key=performance_start)

    for performance in performances:
        print(
            f"{time_range(performance)} | "
            f"{venue_name(data, performance['venue'])} | "
            f"{performance['title']} ({performance_kind(performance)})"
        )


def show_artist(data, slug):
    artist = find_artist(data, slug)

    if artist is None:
        raise ValueError(f"No artist '{slug}'.")

    print(artist["name"])

    performances = [
        performance
        for performance in data["performances"]
        if slug in performance_artists(performance)
    ]
    performances.sort(key=performance_start)

    for performance in performances:
        day = festival_day(performance)
        print(
            f"{day:%a %d} {time_range(performance)} | "
            f"{venue_name(data, performance['venue'])} | "
            f"{performance['title']} ({performance_kind(performance)})"
        )


def show_now(data, moment_text):
    try:
        moment = datetime.fromisoformat(moment_text)
    except ValueError:
        raise ValueError(
            f"'{moment_text}' is not a valid moment, use YYYY-MM-DDTHH:MM."
        ) from None

    performances = sorted(data["performances"], key=performance_start)

    current = [
        performance
        for performance in performances
        if performance_start(performance) <= moment < performance_end(performance)
    ]

    print(f"On stage at {moment:%Y-%m-%d %H:%M}:")

    if current:
        for performance in current:
            print(
                f"- {performance['title']} at "
                f"{venue_name(data, performance['venue'])}, "
                f"until {performance_end(performance):%H:%M}"
            )
    else:
        print("- Nothing is on stage.")

    upcoming = [
        performance
        for performance in performances
        if performance_start(performance) > moment
    ]

    print("Up next:")
    for performance in upcoming[:3]:
        print(
            f"- {time_range(performance)} | "
            f"{venue_name(data, performance['venue'])} | "
            f"{performance['title']} ({performance_kind(performance)})"
        )


# ---------- Validation des nouvelles prestations ----------


def validate_performance(data, title, artist_slug, venue_slug, start, duration):
    if not title.strip():
        raise ValueError("The title cannot be empty.")

    artist = find_artist(data, artist_slug)
    if artist is None:
        raise ValueError(f"No artist '{artist_slug}'.")

    venue = find_venue(data, venue_slug)
    if venue is None:
        raise ValueError(f"No venue '{venue_slug}'.")

    try:
        start = datetime.fromisoformat(start)
    except ValueError:
        raise ValueError(f"Invalid start '{start}', use YYYY-MM-DDTHH:MM.") from None

    try:
        duration = int(duration)
    except (ValueError, TypeError):
        raise ValueError(f"'{duration}' is not a number of minutes.") from None

    if not 1 <= duration <= 360:
        raise ValueError("Duration must be between 1 and 360 minutes.")

    day = start.date()
    first_day = date.fromisoformat(data["first_day"])
    last_day = date.fromisoformat(data["last_day"])

    if not first_day <= day <= last_day:
        raise ValueError(f"{day} is not a day of the festival.")

    new_end = start + timedelta(minutes=duration)
    break_time = timedelta(minutes=BREAK_MINUTES)

    for existing in data["performances"]:
        old_start = performance_start(existing)
        old_end = performance_end(existing)

        # Le lieu doit avoir 30 minutes entre deux prestations.
        if existing["venue"] == venue_slug:
            if start < old_end + break_time and new_end + break_time > old_start:
                old_venue = venue_name(data, existing["venue"])
                raise ValueError(
                    f"{old_venue} is busy with {existing['title']} "
                    f"({old_start:%Y-%m-%d %H:%M}-"
                    f"{old_end:%H:%M})."
                )

        # Tous les rôles d'artiste sont vérifiés.
        if artist_slug in performance_artists(existing):
            if start < old_end + break_time and new_end + break_time > old_start:
                raise ValueError(
                    f"{artist['name']} is on stage in {existing['title']}."
                )

    return {
        "kind": "solo",
        "title": title.strip(),
        "venue": venue_slug,
        "start": start.isoformat(timespec="minutes"),
        "duration_minutes": duration,
        "description": "",
        "artist": artist_slug,
        "min_age": 0,
    }


def add_performance(data):
    title = input("Title: ").strip()
    artist_slug = input("Artist (slug): ").strip()
    venue_slug = input("Venue (slug): ").strip()
    start = input("Start (YYYY-MM-DDTHH:MM): ").strip()
    duration_text = input("Duration (minutes): ").strip()

    performance = validate_performance(
        data, title, artist_slug, venue_slug, start, duration_text
    )

    data["performances"].append(performance)
    save_festival(data)

    print(f"Added: {performance_id(performance)}")


# ---------- Annulation ----------


def cancel_performance(data, identifier):
    for index, performance in enumerate(data["performances"]):
        if performance_id(performance) == identifier:
            title = performance["title"]
            del data["performances"][index]
            save_festival(data)
            print(f"Cancelled: {title}")
            return

    raise ValueError(f"No performance '{identifier}'.")


# ---------- Commandes ----------


def show_help():
    print("Usage:")
    print("  uv run main.py")
    print("  uv run main.py venues")
    print("  uv run main.py programme YYYY-MM-DD")
    print("  uv run main.py artist SLUG")
    print("  uv run main.py now YYYY-MM-DDTHH:MM")
    print("  uv run main.py add")
    print("  uv run main.py cancel ID")


def main():
    try:
        data = read_festival()
        args = sys.argv[1:]

        if not args:
            show_summary(data)
        elif args[0] == "venues" and len(args) == 1:
            show_venues(data)
        elif args[0] == "programme" and len(args) == 2:
            show_programme(data, args[1])
        elif args[0] == "artist" and len(args) == 2:
            show_artist(data, args[1])
        elif args[0] == "now" and len(args) == 2:
            show_now(data, args[1])
        elif args[0] == "add" and len(args) == 1:
            add_performance(data)
        elif args[0] == "cancel" and len(args) == 2:
            cancel_performance(data, args[1])
        else:
            show_help()
            sys.exit(1)

    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"Error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
