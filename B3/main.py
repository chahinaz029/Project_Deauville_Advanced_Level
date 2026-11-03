import sys
from datetime import date, datetime

from festival import DATA_FILE, Festival, Performance


def time_range(performance):
    return f"{performance.start:%H:%M}-{performance.end:%H:%M}"


def show_summary(festival):
    print(festival.name)
    print(f"Venues: {len(festival.venues)}")
    print(f"Artists: {len(festival.artists)}")
    print(f"Performances: {len(festival.performances)}")


def show_venues(festival):
    for venue in festival.venues:
        print(f"{venue.slug} | {venue.name} ({venue.capacity} seats)")


def show_programme(festival, day_text):
    try:
        day = date.fromisoformat(day_text)
    except ValueError:
        raise ValueError(f"'{day_text}' is not a day, use YYYY-MM-DD.") from None

    performances = festival.programme(day=day)

    print(f"Programme for {day:%A %d %B}:")
    for performance in performances:
        print(
            f"{time_range(performance)} | {performance.venue.name} | "
            f"{performance.title} ({performance.kind})"
        )


def show_artist(festival, slug):
    artist = festival.artist(slug)

    print(artist.name)
    for performance in festival.performances_of(artist):
        print(
            f"{performance.festival_day:%a %d} {time_range(performance)} | "
            f"{performance.venue.name} | "
            f"{performance.title} ({performance.kind})"
        )


def show_now(festival, moment_text):
    try:
        moment = datetime.fromisoformat(moment_text)
    except ValueError:
        raise ValueError(
            f"'{moment_text}' is not a valid moment, use YYYY-MM-DDTHH:MM."
        ) from None

    print(f"On stage at {moment:%Y-%m-%d %H:%M}:")

    current = festival.now_playing(moment)
    if current:
        for performance in current:
            print(
                f"- {performance.title} at {performance.venue.name}, "
                f"until {performance.end:%H:%M}"
            )
    else:
        print("- Nothing is on stage.")

    print("Up next:")
    for performance in festival.up_next(moment):
        print(
            f"- {time_range(performance)} | {performance.venue.name} | "
            f"{performance.title} ({performance.kind})"
        )


def ask_and_add(festival):
    title = input("Title: ").strip()
    artist_slug = input("Artist (slug): ").strip()
    venue_slug = input("Venue (slug): ").strip()
    start_text = input("Start (YYYY-MM-DDTHH:MM): ").strip()
    duration_text = input("Duration (minutes): ").strip()

    if not title:
        raise ValueError("The title cannot be empty.")
    artist = festival.artist(artist_slug)
    venue = festival.venue(venue_slug)
    try:
        start = datetime.fromisoformat(start_text)
    except ValueError:
        raise ValueError(
            f"Invalid start '{start_text}', use YYYY-MM-DDTHH:MM."
        ) from None
    try:
        duration = int(duration_text)
    except ValueError:
        raise ValueError(f"'{duration_text}' is not a number of minutes.") from None

    performance = Performance(
        kind="solo",
        title=title,
        venue=venue,
        start=start,
        duration_minutes=duration,
        artist=artist,
    )
    festival.add(performance)
    festival.save()
    print(f"Added: {performance.id}")


def cancel_and_report(festival, identifier):
    performance = festival.cancel(identifier)
    festival.save()
    print(f"Cancelled: {performance.title}")


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
        festival = Festival.from_file(DATA_FILE)
        args = sys.argv[1:]

        if not args:
            show_summary(festival)
        elif args[0] == "venues" and len(args) == 1:
            show_venues(festival)
        elif args[0] == "programme" and len(args) == 2:
            show_programme(festival, args[1])
        elif args[0] == "artist" and len(args) == 2:
            show_artist(festival, args[1])
        elif args[0] == "now" and len(args) == 2:
            show_now(festival, args[1])
        elif args[0] == "add" and len(args) == 1:
            ask_and_add(festival)
        elif args[0] == "cancel" and len(args) == 2:
            cancel_and_report(festival, args[1])
        else:
            show_help()
            sys.exit(1)

    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"Error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
