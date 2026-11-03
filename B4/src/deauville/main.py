"""The `deauville` command (declared in pyproject.toml as deauville.main:main).

    deauville                         summary
    deauville venues
    deauville programme 2027-06-11
    deauville artist SLUG
    deauville now 2027-06-11T21:00
    deauville add
    deauville cancel ID
    deauville serve [--host H] [--port P]

Every command takes `--data FILE` to work on another data file.
Each command function receives a Storage: none of them opens a file itself."""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from deauville.festival import (
    DATA_FILE,
    FestivalError,
    InvalidError,
    JsonStorage,
    SoloShow,
    Storage,
)


def time_range(performance) -> str:
    return f"{performance.start:%H:%M}-{performance.end:%H:%M}"


# ---------- Commands: each one receives the storage ----------


def show_summary(storage: Storage, args: argparse.Namespace) -> None:
    festival = storage.load()
    print(festival.name)
    print(f"Venues: {len(festival.venues)}")
    print(f"Artists: {len(festival.artists)}")
    print(f"Performances: {len(festival.performances)}")


def show_venues(storage: Storage, args: argparse.Namespace) -> None:
    for venue in storage.load().venues:
        print(f"{venue.slug} | {venue.name} ({venue.capacity} seats)")


def show_programme(storage: Storage, args: argparse.Namespace) -> None:
    try:
        day = date.fromisoformat(args.day)
    except ValueError:
        raise InvalidError(f"'{args.day}' is not a day, use YYYY-MM-DD.") from None

    performances = storage.load().programme(day=day)

    print(f"Programme for {day:%A %d %B}:")
    for performance in performances:
        print(
            f"{time_range(performance)} | {performance.venue.name} | "
            f"{performance.title} ({performance.kind})"
        )


def show_artist(storage: Storage, args: argparse.Namespace) -> None:
    festival = storage.load()
    artist = festival.artist(args.slug)

    print(artist.name)
    for performance in festival.performances_of(artist):
        print(
            f"{performance.festival_day:%a %d} {time_range(performance)} | "
            f"{performance.venue.name} | "
            f"{performance.title} ({performance.kind})"
        )


def show_now(storage: Storage, args: argparse.Namespace) -> None:
    try:
        moment = datetime.fromisoformat(args.moment)
    except ValueError:
        raise InvalidError(
            f"'{args.moment}' is not a valid moment, use YYYY-MM-DDTHH:MM."
        ) from None

    festival = storage.load()
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


def ask_and_add(storage: Storage, args: argparse.Namespace) -> None:
    title = input("Title: ").strip()
    artist_slug = input("Artist (slug): ").strip()
    venue_slug = input("Venue (slug): ").strip()
    start_text = input("Start (YYYY-MM-DDTHH:MM): ").strip()
    duration_text = input("Duration (minutes): ").strip()

    festival = storage.load()
    if not title:
        raise InvalidError("The title cannot be empty.")
    artist = festival.artist(artist_slug)
    venue = festival.venue(venue_slug)
    try:
        start = datetime.fromisoformat(start_text)
    except ValueError:
        raise InvalidError(
            f"Invalid start '{start_text}', use YYYY-MM-DDTHH:MM."
        ) from None
    try:
        duration = int(duration_text)
    except ValueError:
        raise InvalidError(f"'{duration_text}' is not a number of minutes.") from None

    performance = SoloShow(
        title=title,
        venue=venue,
        start=start,
        duration_minutes=duration,
        artist=artist,
    )
    festival.add(performance)
    storage.save(festival)
    print(f"Added: {performance.id}")


def cancel_and_report(storage: Storage, args: argparse.Namespace) -> None:
    festival = storage.load()
    performance = festival.cancel(args.id)
    storage.save(festival)
    print(f"Cancelled: {performance.title}")


def serve(storage: Storage, args: argparse.Namespace) -> None:
    # Imported here: the other commands do not need the web part to start.
    import uvicorn

    from deauville.api import create_app

    storage.load()  # a damaged data file is reported now, not on the first request
    print(
        f"Website: http://{args.host}:{args.port}/   Admin: http://{args.host}:{args.port}/admin/"
    )
    uvicorn.run(create_app(storage), host=args.host, port=args.port)


# ---------- Reading the command line ----------


def build_parser() -> argparse.ArgumentParser:
    # --data works before or after the command name; SUPPRESS keeps the two
    # places from overwriting each other.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--data",
        type=Path,
        default=argparse.SUPPRESS,
        metavar="FILE",
        help=f"data file to use (default: {DATA_FILE})",
    )

    parser = argparse.ArgumentParser(
        prog="deauville",
        description="Deauville Festival du Rire.",
        parents=[common],
    )
    commands = parser.add_subparsers(dest="command", metavar="command")

    def command(name, function, help_text):
        sub = commands.add_parser(name, parents=[common], help=help_text)
        sub.set_defaults(function=function)
        return sub

    command("venues", show_venues, "list the venues")
    command("programme", show_programme, "show one day").add_argument(
        "day", help="YYYY-MM-DD"
    )
    command("artist", show_artist, "show one artist").add_argument("slug")
    command("now", show_now, "what is on stage at a moment").add_argument(
        "moment", help="YYYY-MM-DDTHH:MM"
    )
    command("add", ask_and_add, "add a solo show (asks questions)")
    command("cancel", cancel_and_report, "cancel a performance").add_argument("id")
    server = command("serve", serve, "start the website, the admin and the API")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None, storage: Storage | None = None) -> None:
    """Run one command. `storage` lets a test hand in its own."""
    args = build_parser().parse_args(argv)
    if storage is None:
        storage = JsonStorage(getattr(args, "data", DATA_FILE))
    function = getattr(args, "function", show_summary)
    try:
        function(storage, args)
    except (FestivalError, OSError) as error:
        print(f"Error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
