from datetime import datetime

import pytest
from deauville.festival import (
    Artist,
    DataFileError,
    Festival,
    InvalidError,
    Lineup,
    Performance,
    SoloShow,
    Venue,
    Workshop,
)

START = datetime(2027, 6, 11, 20, 0)
HOST = Artist("Tom Vasseur")
ACTS = [Artist("Nora Lebrun"), Artist("Max Pellerin"), Artist("Hugo Lemaire")]


def venue(capacity=120, name="Le Kiosque"):
    return Venue(name, capacity, "Somewhere")


def lineup(duration, acts=None, host=HOST):
    return Lineup(
        title="Gala",
        venue=venue(),
        start=START,
        duration_minutes=duration,
        host=host,
        acts=ACTS if acts is None else acts,
    )


def workshop(max_participants, participants=None, place=None):
    return Workshop(
        title="Lab",
        venue=place or venue(),
        start=START,
        duration_minutes=120,
        teacher=HOST,
        max_participants=max_participants,
        participants=participants or [],
    )


# ---------- Classe abstraite ----------


def test_bare_performance_cannot_be_created():
    with pytest.raises(TypeError):
        Performance(title="x", venue=venue(), start=START, duration_minutes=60)


# ---------- Solo ----------


@pytest.mark.parametrize("age", [0, 16, 18])
def test_solo_valid_min_age(age):
    show = SoloShow(
        title="Solo",
        venue=venue(),
        start=START,
        duration_minutes=60,
        artist=HOST,
        min_age=age,
    )
    assert show.min_age == age


@pytest.mark.parametrize("age", [-1, 19])
def test_solo_invalid_min_age(age):
    with pytest.raises(InvalidError, match="age"):
        SoloShow(
            title="Solo",
            venue=venue(),
            start=START,
            duration_minutes=60,
            artist=HOST,
            min_age=age,
        )


def test_solo_summary_and_view():
    show = SoloShow(
        title="Solo",
        venue=venue(),
        start=START,
        duration_minutes=60,
        artist=HOST,
        min_age=16,
    )
    view = show.to_view()
    assert show.summary == "Tom Vasseur"
    assert view["artist"] == "tom-vasseur"
    assert view["min_age"] == 16
    assert view["kind"] == "solo"


# ---------- Lineup ----------


def test_lineup_of_3_acts_needs_36_minutes():
    with pytest.raises(InvalidError, match="36"):
        lineup(35)
    assert lineup(36).duration_minutes == 36


def test_lineup_of_2_acts_needs_23_minutes():
    with pytest.raises(InvalidError, match="23"):
        lineup(22, acts=ACTS[:2])
    assert lineup(23, acts=ACTS[:2]).duration_minutes == 23


def test_lineup_needs_at_least_2_acts():
    with pytest.raises(InvalidError, match="at least 2"):
        lineup(90, acts=ACTS[:1])


def test_lineup_acts_must_be_different():
    with pytest.raises(InvalidError, match="only once"):
        lineup(90, acts=[ACTS[0], Artist("Nora Lebrun")])


def test_lineup_host_cannot_be_an_act():
    with pytest.raises(InvalidError, match="host"):
        lineup(90, acts=[ACTS[0], Artist("Tom Vasseur")])


def test_lineup_summary_and_view():
    show = lineup(90, acts=ACTS[:2])
    view = show.to_view()
    assert show.summary == "hosted by Tom Vasseur, with Nora Lebrun, Max Pellerin"
    assert view["host"] == "tom-vasseur"
    assert view["acts"] == ["nora-lebrun", "max-pellerin"]
    assert [a["slug"] for a in view["artists"]] == [
        "tom-vasseur",
        "nora-lebrun",
        "max-pellerin",
    ]


# ---------- Workshop ----------


def test_workshop_needs_at_least_one_place():
    with pytest.raises(InvalidError, match="at least 1 place"):
        workshop(0)


def test_workshop_places_are_limited_by_the_venue():
    big_hall = venue(capacity=650, name="Grand Casino")
    show = workshop(999, place=big_hall)
    assert show.places == 650
    assert show.capacity == 650
    assert show.to_view()["capacity"] == 650


def test_workshop_keeps_its_places_when_the_venue_is_larger():
    assert workshop(12).capacity == 12


def test_workshop_summary_and_places_left():
    show = workshop(12, participants=["A", "B", "C"])
    view = show.to_view()
    assert show.summary == "with Tom Vasseur, 3/12 places taken"
    assert view["places_left"] == 9
    assert view["teacher"] == "tom-vasseur"
    assert view["participants"] == ["A", "B", "C"]


# ---------- Chargement depuis les données ----------


def festival_data(*rows):
    return {
        "name": "T",
        "first_day": "2027-06-10",
        "last_day": "2027-06-13",
        "venues": [{"name": "Grand Casino", "capacity": 650, "address": "x"}],
        "artists": [{"name": "Tom Vasseur"}],
        "performances": list(rows),
    }


def test_loader_chooses_the_class_from_the_kind():
    festival = Festival.from_data(
        festival_data(
            {
                "kind": "workshop",
                "title": "Lab",
                "venue": "grand-casino",
                "start": "2027-06-11T10:00",
                "duration_minutes": 120,
                "teacher": "tom-vasseur",
                "max_participants": 999,
            }
        )
    )
    assert isinstance(festival.performances[0], Workshop)
    assert festival.performances[0].capacity == 650


def test_loader_refuses_an_unknown_kind():
    with pytest.raises(DataFileError, match="Unknown performance kind"):
        Festival.from_data(
            festival_data(
                {
                    "kind": "circus",
                    "title": "x",
                    "venue": "grand-casino",
                    "start": "2027-06-11T10:00",
                    "duration_minutes": 60,
                }
            )
        )
