"""Domain tests: the doors are closed, the errors are a family, the rules hold."""

import dataclasses
from datetime import date, datetime

import pytest
from deauville.festival import (
    Artist,
    ConflictError,
    Festival,
    FestivalError,
    InvalidError,
    JsonStorage,
    Lineup,
    NotFoundError,
    SoloShow,
    Workshop,
)

STAND_UP_LAB = "la-cabane-2027-06-12-1030"  # 4 of 10 places taken
MAYA_SOLO = "le-kiosque-2027-06-13-1500"
OPENING_GALA = "grand-casino-2027-06-10-2030"


def solo(
    festival: Festival,
    start: str,
    artist: str = "nora-lebrun",
    venue: str = "le-kiosque",
    minutes: int = 45,
) -> SoloShow:
    return SoloShow(
        title="Nora",
        venue=festival.venue(venue),
        start=datetime.fromisoformat(start),
        duration_minutes=minutes,
        artist=festival.artist(artist),
    )


# ----- closed doors -----


def test_collections_are_read_only_copies(festival):
    assert not hasattr(festival.performances, "append")
    assert not hasattr(festival.artists, "append")
    assert not hasattr(festival.venues, "append")
    with pytest.raises(AttributeError):
        festival.performances = ()  # no setter


def test_a_copy_does_not_reach_the_festival(festival):
    before = len(festival.performances)
    copy = list(festival.performances)
    copy.clear()
    assert len(festival.performances) == before


def test_performances_are_immutable(festival):
    first = festival.programme()[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.start = datetime(2027, 6, 13, 3, 0)


def test_workshop_participants_cannot_be_changed_from_outside(festival):
    workshop = festival.performance(STAND_UP_LAB)
    assert isinstance(workshop.participants, tuple)
    with pytest.raises(AttributeError):
        workshop.participants.append("Intruder")
    assert workshop.places_left == 6


def test_lineup_acts_cannot_be_changed_from_outside(festival):
    lineup = festival.performance(OPENING_GALA)
    assert isinstance(lineup.acts, tuple)
    assert len(lineup.acts) == 4


# ----- the error family -----


def test_every_error_belongs_to_the_family(festival):
    for error in (NotFoundError, ConflictError, InvalidError):
        assert issubclass(error, FestivalError)
    with pytest.raises(FestivalError):
        festival.venue("nowhere")
    with pytest.raises(FestivalError):
        festival.add(solo(festival, "2027-06-13T15:00"))
    with pytest.raises(FestivalError):
        festival.programme(day=date(2030, 1, 1))


def test_types_say_what_went_wrong(festival):
    with pytest.raises(NotFoundError):
        festival.performance("nope")
    with pytest.raises(ConflictError):
        festival.add(solo(festival, "2027-06-13T15:00"))
    with pytest.raises(InvalidError):
        festival.add(solo(festival, "2027-06-13T11:00", minutes=0))


# ----- the step 09 rules, now with the family -----


def test_busy_venue(festival):
    festival.add(solo(festival, "2027-06-13T11:00"))
    with pytest.raises(ConflictError, match="Le Kiosque is busy"):
        festival.add(solo(festival, "2027-06-13T11:30", artist="tom-vasseur"))


def test_artist_cannot_be_on_two_stages(festival):
    festival.add(solo(festival, "2027-06-13T11:00"))
    with pytest.raises(ConflictError, match="Nora Lebrun is on stage"):
        festival.add(solo(festival, "2027-06-13T12:00", venue="grand-casino"))


def test_day_and_duration(festival):
    with pytest.raises(ConflictError, match="not a day of the festival"):
        festival.add(solo(festival, "2027-07-01T11:00"))
    with pytest.raises(InvalidError, match="between 1 and 360"):
        festival.add(solo(festival, "2027-06-13T11:00", minutes=361))


def test_timezone_is_refused(festival):
    with pytest.raises(InvalidError, match="time-zone"):
        festival.add(solo(festival, "2027-06-13T11:00+02:00"))


def test_lineup_rules(festival):
    kiosque = festival.venue("le-kiosque")
    host, a, b = (
        festival.artist(s) for s in ("paul-kerbrat", "hugo-lemaire", "max-pellerin")
    )
    start = datetime(2027, 6, 13, 13, 0)
    with pytest.raises(InvalidError, match="at least 2 acts"):
        Lineup(
            title="L",
            venue=kiosque,
            start=start,
            duration_minutes=60,
            host=host,
            acts=(a,),
        )
    with pytest.raises(InvalidError, match="only once"):
        Lineup(
            title="L",
            venue=kiosque,
            start=start,
            duration_minutes=60,
            host=host,
            acts=(a, a),
        )
    with pytest.raises(InvalidError, match="cannot also be"):
        Lineup(
            title="L",
            venue=kiosque,
            start=start,
            duration_minutes=60,
            host=host,
            acts=(host, a),
        )
    with pytest.raises(InvalidError, match="at least 23 minutes"):
        Lineup(
            title="L",
            venue=kiosque,
            start=start,
            duration_minutes=22,
            host=host,
            acts=(a, b),
        )


def test_workshop_and_solo_rules(festival):
    kiosque = festival.venue("le-kiosque")
    teacher = festival.artist("ines-moreau")
    start = datetime(2027, 6, 13, 13, 0)
    with pytest.raises(InvalidError, match="at least 1 place"):
        Workshop(
            title="W",
            venue=kiosque,
            start=start,
            duration_minutes=60,
            teacher=teacher,
            max_participants=0,
        )
    with pytest.raises(InvalidError, match="between 0 and 18"):
        SoloShow(
            title="S",
            venue=kiosque,
            start=start,
            duration_minutes=60,
            artist=teacher,
            min_age=19,
        )


# ----- moving, cancelling, registering, adding artists -----


def test_update_moves_the_performance_and_changes_its_id(festival):
    first = festival.add(solo(festival, "2027-06-13T11:00"))
    moved = festival.update(first.id, solo(festival, "2027-06-13T12:00"))
    assert moved.id == "le-kiosque-2027-06-13-1200"
    ids = [p.id for p in festival.performances]
    assert "le-kiosque-2027-06-13-1100" not in ids
    assert "le-kiosque-2027-06-13-1200" in ids


def test_a_refused_update_changes_nothing(festival):
    first = festival.add(solo(festival, "2027-06-13T11:00"))
    before = festival.performances
    with pytest.raises(ConflictError):
        festival.update(first.id, solo(festival, "2027-06-13T15:00"))  # Maya is there
    assert festival.performances == before


def test_a_performance_does_not_clash_with_itself(festival):
    first = festival.add(solo(festival, "2027-06-13T11:00"))
    festival.update(first.id, solo(festival, "2027-06-13T11:10", minutes=30))


def test_cancel(festival):
    festival.cancel(MAYA_SOLO)
    with pytest.raises(NotFoundError):
        festival.performance(MAYA_SOLO)


def test_register_rules(festival):
    festival.register(STAND_UP_LAB, "Camille Roy")
    with pytest.raises(ConflictError, match="already registered"):
        festival.register(STAND_UP_LAB, "camille  roy")
    with pytest.raises(ConflictError, match="already registered"):
        festival.register(STAND_UP_LAB, "chloe d.")  # same as "Chloé D."
    with pytest.raises(InvalidError, match="not a workshop"):
        festival.register(MAYA_SOLO, "Camille Roy")
    with pytest.raises(InvalidError, match="needs a name"):
        festival.register(STAND_UP_LAB, "  ")


def test_a_full_workshop_refuses_more(festival):
    for number in range(6):  # 4 + 6 = the 10 places
        festival.register(STAND_UP_LAB, f"Guest {number}")
    assert festival.performance(STAND_UP_LAB).places_left == 0
    with pytest.raises(ConflictError, match="is full"):
        festival.register(STAND_UP_LAB, "One Too Many")


def test_a_workshop_update_keeps_its_participants(festival):
    workshop = festival.performance(STAND_UP_LAB)
    new = dataclasses.replace(workshop, start=datetime(2027, 6, 12, 14, 0))
    moved = festival.update(workshop.id, new)
    assert moved.participants == workshop.participants
    assert len(moved.participants) == 4


def test_a_workshop_with_participants_cannot_become_a_solo(festival):
    workshop = festival.performance(STAND_UP_LAB)
    with pytest.raises(ConflictError, match="must stay a workshop"):
        festival.update(
            workshop.id, solo(festival, "2027-06-12T10:30", venue="la-cabane")
        )


def test_a_workshop_refuses_the_same_participant_twice(festival):
    workshop = festival.performance(STAND_UP_LAB)
    with pytest.raises(InvalidError, match="only once"):
        dataclasses.replace(workshop, participants=("Chloé D.", "chloe d."))


def test_add_artist_twice(festival):
    festival.add_artist(Artist(name="Zoé Tanguy"))
    with pytest.raises(ConflictError, match="already exists"):
        festival.add_artist(Artist(name="zoe tanguy"))
    with pytest.raises(InvalidError):
        festival.add_artist(Artist(name="  "))
    assert festival.artist("zoe-tanguy").name == "Zoé Tanguy"


def test_save_and_reload(festival, data_file):
    festival.add(solo(festival, "2027-06-13T11:00"))
    festival.register(STAND_UP_LAB, "Camille Roy")
    JsonStorage(data_file).save(festival)
    again = JsonStorage(data_file).load()
    assert again.performance("le-kiosque-2027-06-13-1100").summary == "Nora Lebrun"
    assert "Camille Roy" in again.performance(STAND_UP_LAB).participants
    assert not data_file.with_name("festival.json.tmp").exists()


def test_the_real_data_file_loads_unchanged(festival, data_file):
    """Loading then saving the real data must not lose or reorder anything."""
    before = len(festival.performances)
    JsonStorage(data_file).save(festival)
    again = JsonStorage(data_file).load()
    assert len(again.performances) == before == 23
    assert [p.id for p in again.programme()] == [p.id for p in festival.programme()]
