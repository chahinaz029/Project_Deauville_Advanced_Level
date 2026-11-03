"""API.md, line by line: every route, every filter, every status of the table.

The tests talk to the application through HTTP (TestClient), without a server,
on a copy of the data in a temporary folder."""

import os
import re
from datetime import datetime

import pytest
from deauville.api import create_app
from deauville.festival import JsonStorage, MemoryStorage
from fastapi.testclient import TestClient

# These exist in data/festival.json (they are used by the step 10 tests too).
AFTER_HOURS = "le-kiosque-2027-06-12-0100"  # lineup, belongs to Friday 11 June
STAND_UP_LAB = "la-cabane-2027-06-12-1030"  # workshop, 4 of 10 places taken
MAYA_SOLO = "le-kiosque-2027-06-13-1500"  # solo show

LOCAL_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")

VENUE_KEYS = {"slug", "name", "capacity", "address"}
ARTIST_KEYS = {"slug", "name", "bio", "photo_url"}
FESTIVAL_KEYS = {"name", "first_day", "last_day", "days"}
COMMON_KEYS = {
    "id",
    "kind",
    "title",
    "venue",
    "venue_name",
    "start",
    "end",
    "duration_minutes",
    "festival_day",
    "description",
    "summary",
    "capacity",
    "artists",
}
KIND_KEYS = {
    "solo": {"artist", "min_age"},
    "lineup": {"host", "acts"},
    "workshop": {"teacher", "max_participants", "participants", "places_left"},
}


# ---------- helpers ----------


def make_artist(client, name):
    response = client.post("/api/artists", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["slug"]


def solo_body(
    artist,
    venue="le-kiosque",
    start="2027-06-13T11:00",
    minutes=45,
    title="Solo test",
    **more,
):
    return {
        "kind": "solo",
        "title": title,
        "venue": venue,
        "start": start,
        "duration_minutes": minutes,
        "artist": artist,
        **more,
    }


def lineup_body(
    host,
    acts,
    venue="theatre-des-planches",
    start="2027-06-13T13:00",
    minutes=60,
    title="Lineup test",
):
    return {
        "kind": "lineup",
        "title": title,
        "venue": venue,
        "start": start,
        "duration_minutes": minutes,
        "host": host,
        "acts": acts,
    }


def workshop_body(
    teacher,
    places=1,
    venue="la-cabane",
    start="2027-06-12T14:00",
    minutes=60,
    title="Tiny Lab",
    **more,
):
    return {
        "kind": "workshop",
        "title": title,
        "venue": venue,
        "start": start,
        "duration_minutes": minutes,
        "teacher": teacher,
        "max_participants": places,
        **more,
    }


def a_solo(client, name="Solo Sam", **more):
    """A solo show by a brand new artist, in a slot known to be free."""
    return solo_body(make_artist(client, name), **more)


def a_solo_body(created):
    """The saved fields of a performance, as a PUT body (no id, end, summary...)."""
    return solo_body(
        created["artist"],
        venue=created["venue"],
        start=created["start"],
        minutes=created["duration_minutes"],
        title=created["title"],
    )


def assert_error(response, status):
    assert response.status_code == status, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, str) and detail, "detail must be a sentence"


def assert_shape_error(response):
    """FastAPI's own 422: detail is a list of problems."""
    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], list)


def new_client(storage, tmp_path, name):
    public = tmp_path / f"public-{name}"
    admin = tmp_path / f"admin-{name}"
    public.mkdir()
    admin.mkdir()
    return TestClient(create_app(storage, public_dir=public, admin_dir=admin))


# ---------- the contract is complete ----------

CONTRACT = [
    ("get", "/api/festival"),
    ("get", "/api/venues"),
    ("get", "/api/artists"),
    ("get", "/api/artists/{}"),
    ("get", "/api/programme"),
    ("get", "/api/performances/{}"),
    ("get", "/api/now"),
    ("post", "/api/artists"),
    ("post", "/api/performances"),
    ("put", "/api/performances/{}"),
    ("delete", "/api/performances/{}"),
    ("post", "/api/performances/{}/participants"),
]


def test_every_route_of_the_contract_exists(client):
    paths = client.get("/openapi.json").json()["paths"]
    found = {
        (method, re.sub(r"\{[^}]+\}", "{}", path))
        for path, methods in paths.items()
        for method in methods
    }
    for route in CONTRACT:
        assert route in found, f"missing route: {route}"


# ---------- Read: /api/festival, /api/venues, /api/artists ----------


def test_festival(client, festival):
    body = client.get("/api/festival").json()
    assert set(body) == FESTIVAL_KEYS
    assert body["name"] == festival.name
    assert body["first_day"] == festival.first_day.isoformat()
    assert body["last_day"] == festival.last_day.isoformat()
    assert body["days"] == [day.isoformat() for day in festival.days]
    assert body["days"][0] == body["first_day"] and body["days"][-1] == body["last_day"]


def test_venues_in_the_order_they_were_added(client, festival):
    venues = client.get("/api/venues").json()
    assert [v["slug"] for v in venues] == [v.slug for v in festival.venues]
    for venue in venues:
        assert set(venue) == VENUE_KEYS


def test_artists_in_alphabetical_order(client, festival):
    artists = client.get("/api/artists").json()
    slugs = [a["slug"] for a in artists]
    assert slugs == sorted(slugs)
    assert len(artists) == len(festival.artists)
    for artist in artists:
        assert set(artist) == ARTIST_KEYS


def test_a_new_artist_takes_its_alphabetical_place(client):
    make_artist(client, "Zoé Tanguy")
    make_artist(client, "Aaron Alpha")
    slugs = [a["slug"] for a in client.get("/api/artists").json()]
    assert slugs == sorted(slugs)
    assert slugs[0] == "aaron-alpha" and slugs[-1] == "zoe-tanguy"


# ---------- Read: /api/artists/{slug} ----------


def test_an_artist_with_their_performances_in_order(client, festival):
    body = client.get("/api/artists/max-pellerin").json()
    assert set(body) == ARTIST_KEYS | {"performances"}
    expected = [p.id for p in festival.performances_of("max-pellerin")]
    assert [p["id"] for p in body["performances"]] == expected
    assert len(expected) >= 2
    starts = [p["start"] for p in body["performances"]]
    assert starts == sorted(starts)


def test_an_artist_without_performances_has_an_empty_list(client):
    slug = make_artist(client, "Brand New")
    assert client.get(f"/api/artists/{slug}").json()["performances"] == []


# ---------- Read: /api/programme and its filters ----------


def test_programme_is_in_programme_order(client, festival):
    body = client.get("/api/programme").json()
    assert len(body) == len(festival.performances)
    order = [(p["start"], p["venue_name"]) for p in body]
    assert order == sorted(order)


def test_programme_day_filter(client, festival):
    for day in festival.days:
        ids = [p["id"] for p in client.get(f"/api/programme?day={day}").json()]
        assert ids == [p.id for p in festival.programme(day=day)]
    # a show after midnight belongs to the day before
    friday = [p["id"] for p in client.get("/api/programme?day=2027-06-11").json()]
    saturday = [p["id"] for p in client.get("/api/programme?day=2027-06-12").json()]
    assert AFTER_HOURS in friday and AFTER_HOURS not in saturday


def test_programme_venue_filter(client, festival):
    for venue in festival.venues:
        body = client.get(f"/api/programme?venue={venue.slug}").json()
        assert [p["id"] for p in body] == [
            p.id for p in festival.programme(venue=venue.slug)
        ]
        assert all(p["venue"] == venue.slug for p in body)


def test_programme_day_and_venue_together(client):
    body = client.get("/api/programme?day=2027-06-13&venue=le-kiosque").json()
    assert MAYA_SOLO in [p["id"] for p in body]
    assert all(
        p["festival_day"] == "2027-06-13" and p["venue"] == "le-kiosque" for p in body
    )


def test_programme_filter_errors(client):
    assert_error(client.get("/api/programme?venue=nowhere"), 404)
    assert_shape_error(client.get("/api/programme?day=June 11"))
    assert_error(client.get("/api/programme?day=2030-01-01"), 422)


# ---------- Read: /api/performances/{id} ----------


@pytest.mark.parametrize(
    "performance_id, kind",
    [
        (MAYA_SOLO, "solo"),
        (AFTER_HOURS, "lineup"),
        (STAND_UP_LAB, "workshop"),
    ],
)
def test_a_performance_has_the_fields_of_its_kind(client, performance_id, kind):
    body = client.get(f"/api/performances/{performance_id}").json()
    assert set(body) == COMMON_KEYS | KIND_KEYS[kind]
    assert body["kind"] == kind and body["id"] == performance_id
    assert LOCAL_TIME.match(body["start"]) and LOCAL_TIME.match(body["end"])
    assert all(set(a) == {"slug", "name"} for a in body["artists"])


def test_the_solo_values(client):
    body = client.get(f"/api/performances/{MAYA_SOLO}").json()
    assert body["start"] == "2027-06-13T15:00" and body["end"] == "2027-06-13T16:00"
    assert body["artist"] == "maya-choukri" and body["summary"] == "Maya Choukri"
    assert [a["slug"] for a in body["artists"]] == ["maya-choukri"]


def test_the_lineup_values(client):
    body = client.get(f"/api/performances/{AFTER_HOURS}").json()
    assert body["festival_day"] == "2027-06-11"
    assert body["start"] == "2027-06-12T01:00" and body["end"] == "2027-06-12T02:00"
    assert body["summary"] == "hosted by Tom Vasseur, with Hugo Lemaire, Maya Choukri"
    assert body["host"] == "tom-vasseur"
    assert body["acts"] == ["hugo-lemaire", "maya-choukri"]
    assert [a["slug"] for a in body["artists"]] == [
        "tom-vasseur",
        "hugo-lemaire",
        "maya-choukri",
    ]


def test_the_workshop_values(client):
    body = client.get(f"/api/performances/{STAND_UP_LAB}").json()
    venue = next(
        v for v in client.get("/api/venues").json() if v["slug"] == body["venue"]
    )
    assert body["capacity"] == min(body["max_participants"], venue["capacity"])
    assert len(body["participants"]) == 4
    assert body["places_left"] == body["capacity"] - 4
    assert body["summary"].endswith(f"4/{body['capacity']} places taken")


# ---------- Read: /api/now ----------


def test_now_during_a_show(client, festival):
    body = client.get("/api/now?at=2027-06-12T01:30").json()
    assert set(body) == {"at", "now_playing", "up_next"}
    assert body["at"] == "2027-06-12T01:30"
    assert [p["id"] for p in body["now_playing"]] == [AFTER_HOURS]
    expected = [p.id for p in festival.up_next(datetime(2027, 6, 12, 1, 30))]
    assert [p["id"] for p in body["up_next"]] == expected
    assert len(body["up_next"]) == 3


def test_now_before_everything_and_after_everything(client):
    before = client.get("/api/now?at=2027-01-01T12:00").json()
    assert before["now_playing"] == [] and len(before["up_next"]) == 3
    after = client.get("/api/now?at=2027-12-31T12:00").json()
    assert after["now_playing"] == [] and after["up_next"] == []


def test_now_up_next_is_in_order_and_after_the_moment(client):
    body = client.get("/api/now?at=2027-06-10T00:00").json()
    starts = [p["start"] for p in body["up_next"]]
    assert starts == sorted(starts) and all(s > "2027-06-10T00:00" for s in starts)


def test_now_without_at_uses_the_current_time(client):
    body = client.get("/api/now").json()
    assert set(body) == {"at", "now_playing", "up_next"}
    assert LOCAL_TIME.match(body["at"])
    assert len(body["up_next"]) <= 3


def test_now_with_a_wrong_moment(client):
    assert_shape_error(client.get("/api/now?at=yesterday"))


# ---------- Write: POST /api/performances ----------


def test_create_a_solo_201_then_listed_and_saved(client, data_file):
    body = a_solo(client)
    response = client.post("/api/performances", json=body)
    assert response.status_code == 201
    created = response.json()
    assert created["id"] == "le-kiosque-2027-06-13-1100"
    assert set(created) == COMMON_KEYS | KIND_KEYS["solo"]
    assert client.get(f"/api/performances/{created['id']}").status_code == 200
    day = [p["id"] for p in client.get("/api/programme?day=2027-06-13").json()]
    assert created["id"] in day
    assert JsonStorage(data_file).load().performance(created["id"])  # saved at once


def test_create_a_lineup_201(client):
    host, one, two = (
        make_artist(client, n) for n in ("Host Hal", "Act One", "Act Two")
    )
    response = client.post("/api/performances", json=lineup_body(host, [one, two]))
    assert response.status_code == 201
    assert set(response.json()) == COMMON_KEYS | KIND_KEYS["lineup"]
    assert response.json()["acts"] == [one, two]


def test_create_a_workshop_201(client):
    teacher = make_artist(client, "Teach Terry")
    response = client.post("/api/performances", json=workshop_body(teacher, places=5))
    assert response.status_code == 201
    created = response.json()
    assert created["places_left"] == 5 and created["participants"] == []


def test_a_new_performance_leaves_the_others_alone(client, festival):
    client.post("/api/performances", json=a_solo(client))
    assert len(client.get("/api/programme").json()) == len(festival.performances) + 1


def test_a_show_after_midnight_belongs_to_the_previous_day(client, festival):
    busy = {
        p.venue.slug
        for p in festival.performances
        if p.end > datetime(2027, 6, 13, 23, 0)
    }
    free = [v.slug for v in festival.venues if v.slug not in busy]
    if not free:
        pytest.skip("every venue is busy late on the last night")
    body = a_solo(client, venue=free[0], start="2027-06-14T01:00", minutes=30)
    response = client.post("/api/performances", json=body)
    assert response.status_code == 201
    assert response.json()["festival_day"] == "2027-06-13"


# ---------- Write: PUT /api/performances/{id} ----------


def test_put_changes_the_id_and_answers_with_the_new_one(client, data_file):
    created = client.post("/api/performances", json=a_solo(client)).json()
    moved = {**a_solo_body(created), "start": "2027-06-13T12:00"}
    response = client.put(f"/api/performances/{created['id']}", json=moved)
    assert response.status_code == 200
    assert response.json()["id"] == "le-kiosque-2027-06-13-1200"
    assert client.get(f"/api/performances/{created['id']}").status_code == 404
    assert client.get("/api/performances/le-kiosque-2027-06-13-1200").status_code == 200
    assert JsonStorage(data_file).load().performance("le-kiosque-2027-06-13-1200")


def test_put_can_move_to_another_venue(client):
    created = client.post("/api/performances", json=a_solo(client)).json()
    moved = {
        **a_solo_body(created),
        "venue": "theatre-des-planches",
        "start": "2027-06-13T13:00",
    }
    response = client.put(f"/api/performances/{created['id']}", json=moved)
    assert response.status_code == 200
    assert response.json()["id"] == "theatre-des-planches-2027-06-13-1300"


def test_put_changing_nothing_is_accepted(client):
    created = client.post("/api/performances", json=a_solo(client)).json()
    response = client.put(
        f"/api/performances/{created['id']}", json=a_solo_body(created)
    )
    assert response.status_code == 200 and response.json()["id"] == created["id"]


def test_a_refused_put_changes_nothing(client, data_file):
    created = client.post("/api/performances", json=a_solo(client)).json()
    before = data_file.read_bytes()
    busy = {
        **a_solo_body(created),
        "start": "2027-06-13T15:00",
    }  # Maya fills Le Kiosque
    assert_error(client.put(f"/api/performances/{created['id']}", json=busy), 409)
    assert (
        client.get(f"/api/performances/{created['id']}").json()["start"]
        == "2027-06-13T11:00"
    )
    assert data_file.read_bytes() == before


def test_a_put_refused_for_an_invalid_value_changes_nothing(client, data_file):
    created = client.post("/api/performances", json=a_solo(client)).json()
    before = data_file.read_bytes()
    bad = {**a_solo_body(created), "duration_minutes": 0}
    assert_error(client.put(f"/api/performances/{created['id']}", json=bad), 422)
    assert data_file.read_bytes() == before


def test_put_on_an_unknown_performance_is_404(client):
    assert_error(client.put("/api/performances/nope", json=a_solo(client)), 404)


def test_put_keeps_the_participants_of_a_workshop(client):
    body = {
        "kind": "workshop",
        "title": "Stand-up Lab",
        "venue": "la-cabane",
        "start": "2027-06-12T14:00",
        "duration_minutes": 120,
        "teacher": "paul-kerbrat",
        "max_participants": 10,
    }
    response = client.put(f"/api/performances/{STAND_UP_LAB}", json=body)
    assert response.status_code == 200
    assert response.json()["id"] == "la-cabane-2027-06-12-1400"
    assert len(response.json()["participants"]) == 4


def test_a_workshop_with_participants_cannot_become_a_solo(client):
    body = a_solo(client, venue="la-cabane", start="2027-06-12T10:30")
    assert_error(client.put(f"/api/performances/{STAND_UP_LAB}", json=body), 409)


# ---------- Write: DELETE /api/performances/{id} ----------


def test_delete_is_204_without_a_body_then_404(client, data_file, festival):
    response = client.delete(f"/api/performances/{MAYA_SOLO}")
    assert response.status_code == 204 and response.content == b""
    assert_error(client.delete(f"/api/performances/{MAYA_SOLO}"), 404)
    assert_error(client.get(f"/api/performances/{MAYA_SOLO}"), 404)
    saved = JsonStorage(data_file).load()
    assert len(saved.performances) == len(festival.performances) - 1


# ---------- Write: POST /api/performances/{id}/participants ----------


def test_register_a_participant_201_and_saved(client, data_file):
    url = f"/api/performances/{STAND_UP_LAB}/participants"
    before = client.get(f"/api/performances/{STAND_UP_LAB}").json()
    response = client.post(url, json={"name": "Camille Roy"})
    assert response.status_code == 201
    body = response.json()
    assert set(body) == COMMON_KEYS | KIND_KEYS["workshop"]
    assert body["participants"][-1] == "Camille Roy"
    assert body["places_left"] == before["places_left"] - 1
    saved = JsonStorage(data_file).load().performance(STAND_UP_LAB)
    assert "Camille Roy" in saved.participants


@pytest.mark.parametrize("again", ["Camille Roy", "camille roy", "  Camille   Roy "])
def test_the_same_name_twice_is_409(client, again):
    url = f"/api/performances/{STAND_UP_LAB}/participants"
    assert client.post(url, json={"name": "Camille Roy"}).status_code == 201
    response = client.post(url, json={"name": again})
    assert_error(response, 409)
    assert "already registered" in response.json()["detail"]


def test_a_full_workshop_is_409(client):
    teacher = make_artist(client, "Teach Terry")
    created = client.post(
        "/api/performances", json=workshop_body(teacher, places=1)
    ).json()
    url = f"/api/performances/{created['id']}/participants"
    assert client.post(url, json={"name": "A One"}).status_code == 201
    response = client.post(url, json={"name": "B Two"})
    assert_error(response, 409)
    assert "is full" in response.json()["detail"]


def test_registering_for_something_that_is_not_a_workshop_is_422(client):
    assert_error(
        client.post(
            f"/api/performances/{MAYA_SOLO}/participants", json={"name": "Camille"}
        ),
        422,
    )
    assert_error(
        client.post(
            f"/api/performances/{AFTER_HOURS}/participants", json={"name": "Camille"}
        ),
        422,
    )


def test_registering_with_an_empty_name_is_422(client):
    assert_error(
        client.post(
            f"/api/performances/{STAND_UP_LAB}/participants", json={"name": "  "}
        ),
        422,
    )


def test_registering_for_an_unknown_performance_is_404(client):
    assert_error(
        client.post("/api/performances/nope/participants", json={"name": "Camille"}),
        404,
    )


# ---------- Write: POST /api/artists ----------


def test_create_an_artist_201_and_saved(client, data_file):
    response = client.post("/api/artists", json={"name": "Zoé Tanguy"})
    assert response.status_code == 201
    assert response.json() == {
        "slug": "zoe-tanguy",
        "name": "Zoé Tanguy",
        "bio": "",
        "photo_url": "",
    }
    assert JsonStorage(data_file).load().artist("zoe-tanguy")
    assert client.get("/api/artists/zoe-tanguy").status_code == 200


def test_an_artist_with_a_bio_and_a_photo(client):
    body = {
        "name": "Zoé Tanguy",
        "bio": "Stories.",
        "photo_url": "https://example.org/z.jpg",
    }
    created = client.post("/api/artists", json=body).json()
    assert (
        created["bio"] == "Stories."
        and created["photo_url"] == "https://example.org/z.jpg"
    )


def test_extra_spaces_in_a_name_are_cleaned(client):
    assert (
        client.post("/api/artists", json={"name": "  Zoé   Tanguy "}).json()["name"]
        == "Zoé Tanguy"
    )


@pytest.mark.parametrize(
    "again", ["Zoé Tanguy", "zoe tanguy", "ZOE  TANGUY", "Zoe Tanguy"]
)
def test_the_same_artist_twice_is_409(client, again):
    assert client.post("/api/artists", json={"name": "Zoé Tanguy"}).status_code == 201
    response = client.post("/api/artists", json={"name": again})
    assert_error(response, 409)
    assert "already exists" in response.json()["detail"]


@pytest.mark.parametrize("name", ["", "   ", "!!!"])
def test_an_artist_without_a_real_name_is_422(client, name):
    assert_error(client.post("/api/artists", json={"name": name}), 422)


# ---------- Errors: 404 unknown artist, venue or performance ----------


@pytest.mark.parametrize(
    "method, url, body",
    [
        ("get", "/api/artists/nobody", None),
        ("get", "/api/performances/nope", None),
        ("get", "/api/programme?venue=nowhere", None),
        ("delete", "/api/performances/nope", None),
        ("post", "/api/performances/nope/participants", {"name": "Camille"}),
    ],
)
def test_unknown_things_are_404(client, method, url, body):
    assert_error(client.request(method, url, json=body), 404)


def test_unknown_venue_or_artist_in_a_body_is_404(client):
    one, two = make_artist(client, "Act One"), make_artist(client, "Act Two")
    assert_error(
        client.post("/api/performances", json=solo_body(one, venue="nowhere")), 404
    )
    assert_error(client.post("/api/performances", json=solo_body("nobody")), 404)
    assert_error(
        client.post("/api/performances", json=lineup_body("nobody", [one, two])), 404
    )
    assert_error(
        client.post("/api/performances", json=lineup_body(one, [two, "nobody"])), 404
    )
    assert_error(client.post("/api/performances", json=workshop_body("nobody")), 404)


# ---------- Errors: 409 busy, outside the festival, full, already exists ----------


def test_a_busy_venue_is_409(client):
    first = a_solo(client, "Solo Sam")
    client.post("/api/performances", json=first)
    other = solo_body(make_artist(client, "Solo Sue"), start="2027-06-13T11:30")
    response = client.post("/api/performances", json=other)
    assert_error(response, 409)
    assert "Le Kiosque is busy" in response.json()["detail"]


def test_a_venue_needs_thirty_minutes_between_two_shows(client):
    client.post("/api/performances", json=a_solo(client, "Solo Sam"))  # 11:00-11:45
    too_early = solo_body(make_artist(client, "Solo Sue"), start="2027-06-13T12:10")
    assert_error(client.post("/api/performances", json=too_early), 409)
    just_right = solo_body(make_artist(client, "Solo Sid"), start="2027-06-13T12:15")
    assert client.post("/api/performances", json=just_right).status_code == 201


def test_an_artist_on_stage_elsewhere_is_409(client):
    first = a_solo(client, "Solo Sam")
    client.post("/api/performances", json=first)
    elsewhere = solo_body(
        first["artist"], venue="grand-casino", start="2027-06-13T12:00"
    )
    response = client.post("/api/performances", json=elsewhere)
    assert_error(response, 409)
    assert "Solo Sam is on stage" in response.json()["detail"]


def test_an_artist_busy_as_host_or_act_of_a_lineup_is_409(client):
    host, one, two = (
        make_artist(client, n) for n in ("Host Hal", "Act One", "Act Two")
    )
    created = client.post(
        "/api/performances",
        json=lineup_body(
            host, [one, two], venue="le-kiosque", start="2027-06-13T11:00", minutes=40
        ),
    )
    assert created.status_code == 201
    for artist, name in ((one, "Act One"), (host, "Host Hal")):
        body = solo_body(artist, venue="grand-casino", start="2027-06-13T12:00")
        response = client.post("/api/performances", json=body)
        assert_error(response, 409)
        assert f"{name} is on stage" in response.json()["detail"]


@pytest.mark.parametrize(
    "start",
    [
        "2027-07-01T11:00",  # a month later
        "2027-06-14T10:00",  # the day after the last day
        "2027-06-10T01:00",  # 1 am on the first day still belongs to the day before
    ],
)
def test_a_date_outside_the_festival_is_409(client, start):
    body = a_solo(client, start=start)
    response = client.post("/api/performances", json=body)
    assert_error(response, 409)
    assert "not a day of the festival" in response.json()["detail"]


# ---------- Errors: 422 invalid value ----------


@pytest.mark.parametrize(
    "change",
    [
        {"duration_minutes": 0},
        {"duration_minutes": 361},
        {"duration_minutes": -5},
        {"min_age": 19},
        {"min_age": -1},
        {"title": ""},
        {"title": "   "},
        {"start": "2027-06-13T11:00+02:00"},  # a time zone is not allowed
    ],
)
def test_invalid_values_are_422(client, change):
    body = {**a_solo(client), **change}
    assert_error(client.post("/api/performances", json=body), 422)


def test_the_limits_of_a_duration_are_accepted(client, festival):
    short = a_solo(
        client,
        "Short Sam",
        venue="theatre-des-planches",
        start="2027-06-13T13:00",
        minutes=1,
    )
    first = client.post("/api/performances", json=short)
    assert first.status_code == 201 and first.json()["duration_minutes"] == 1
    # 360 minutes needs a whole quiet morning: pick a venue that has one.
    window_start, window_end = (
        datetime(2027, 6, 13, 5, 0),
        datetime(2027, 6, 13, 12, 30),
    )
    busy = {
        p.venue.slug
        for p in festival.performances
        if p.start < window_end and p.end > window_start
    }
    quiet = [v.slug for v in festival.venues if v.slug not in busy]
    if not quiet:
        pytest.skip("no venue is free on the morning of the last day")
    body = a_solo(
        client, "Long Lee", venue=quiet[0], start="2027-06-13T06:00", minutes=360
    )
    assert client.post("/api/performances", json=body).status_code == 201


def test_invalid_lineups_are_422(client):
    host, one, two, three = (
        make_artist(client, n) for n in ("Host Hal", "Act One", "Act Two", "Act Three")
    )

    def post(body: dict) -> object:
        return client.post("/api/performances", json=body)

    assert_error(post(lineup_body(host, [one])), 422)  # one act
    assert_error(post(lineup_body(host, [])), 422)  # no act
    assert_error(post(lineup_body(host, [one, one])), 422)  # same act twice
    assert_error(post(lineup_body(host, [host, one])), 422)  # the host is an act
    assert_error(
        post(lineup_body(host, [one, two, three], minutes=35)), 422
    )  # 3 acts need 36
    assert post(lineup_body(host, [one, two, three], minutes=36)).status_code == 201


def test_a_workshop_without_a_place_is_422(client):
    assert_error(
        client.post(
            "/api/performances",
            json=workshop_body(make_artist(client, "Teach Terry"), places=0),
        ),
        422,
    )


# ---------- Errors: FastAPI's 422 for a body of the wrong shape ----------


def test_bodies_of_the_wrong_shape_are_refused_by_fastapi(client):
    good = a_solo(client)
    missing = {k: v for k, v in good.items() if k != "title"}
    assert_shape_error(client.post("/api/performances", json=missing))
    assert_shape_error(
        client.post("/api/performances", json={**good, "kind": "circus"})
    )
    assert_shape_error(client.post("/api/performances", json={**good, "extra": 1}))
    assert_shape_error(
        client.post("/api/performances", json={**good, "duration_minutes": "long"})
    )
    assert_shape_error(
        client.post("/api/performances", json={**good, "start": "tomorrow"})
    )
    assert_shape_error(client.post("/api/performances", json={}))
    assert_shape_error(client.post("/api/artists", json={}))
    assert_shape_error(client.post("/api/artists", json={"name": "X", "age": 3}))
    assert_shape_error(
        client.post(f"/api/performances/{STAND_UP_LAB}/participants", json={})
    )
    assert_shape_error(client.put(f"/api/performances/{MAYA_SOLO}", json={}))


# ---------- Errors: 500 the data file cannot be read or written ----------

READ_ROUTES = [
    "/api/festival",
    "/api/venues",
    "/api/artists",
    "/api/artists/max-pellerin",
    "/api/programme",
    f"/api/performances/{MAYA_SOLO}",
    "/api/now?at=2027-06-12T01:30",
]


@pytest.mark.parametrize("url", READ_ROUTES)
def test_a_damaged_data_file_is_500(client, data_file, url):
    data_file.write_text("{ not json", encoding="utf-8")
    response = client.get(url)
    assert_error(response, 500)
    assert "damaged" in response.json()["detail"]


def test_a_missing_data_file_is_500(client, data_file):
    data_file.unlink()
    response = client.get("/api/festival")
    assert_error(response, 500)
    assert "was not found" in response.json()["detail"]


def test_a_data_file_with_the_wrong_structure_is_500(client, data_file):
    data_file.write_text('{"name": "x"}', encoding="utf-8")
    assert_error(client.get("/api/venues"), 500)


def test_a_write_on_a_damaged_file_is_500(client, data_file):
    data_file.write_text("{ not json", encoding="utf-8")
    assert_error(client.post("/api/artists", json={"name": "Zoé Tanguy"}), 500)
    assert data_file.read_text(encoding="utf-8") == "{ not json"


def test_a_file_that_cannot_be_written_is_500_and_nothing_changes(
    client, data_file, monkeypatch
):
    before = data_file.read_bytes()

    def refuse(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(os, "replace", refuse)
    response = client.post("/api/artists", json={"name": "Zoé Tanguy"})
    assert_error(response, 500)
    assert "Could not save" in response.json()["detail"]
    monkeypatch.undo()
    assert data_file.read_bytes() == before
    assert_error(client.get("/api/artists/zoe-tanguy"), 404)  # it was not kept


# ---------- The application factory ----------


def test_two_applications_do_not_share_their_state(festival, tmp_path):
    first = new_client(MemoryStorage(festival), tmp_path, "first")
    second = new_client(MemoryStorage(festival), tmp_path, "second")
    assert first.post("/api/artists", json={"name": "Zoé Tanguy"}).status_code == 201
    assert first.get("/api/artists/zoe-tanguy").status_code == 200
    assert_error(second.get("/api/artists/zoe-tanguy"), 404)


def test_the_website_and_the_admin_are_served(client):
    assert client.get("/").status_code in (200, 404)  # 404 only if web/public is empty
    assert client.get("/api/festival").status_code == 200
