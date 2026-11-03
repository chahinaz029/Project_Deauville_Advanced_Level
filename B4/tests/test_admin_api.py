"""The 'Vérifier' table of step 10, line by line, through the API."""

from deauville.festival import JsonStorage

SOLO = {
    "kind": "solo",
    "title": "Nora en solo",
    "venue": "le-kiosque",
    "start": "2027-06-13T11:00",
    "duration_minutes": 45,
    "artist": "nora-lebrun",
}
STAND_UP_LAB = "la-cabane-2027-06-12-1030"  # 4 of 10 places taken
MAYA_SOLO = "le-kiosque-2027-06-13-1500"


def test_solo_is_created_listed_and_saved(client, data_file):
    response = client.post("/api/performances", json=SOLO)
    assert response.status_code == 201
    assert response.json()["id"] == "le-kiosque-2027-06-13-1100"
    assert client.get("/api/performances/le-kiosque-2027-06-13-1100").status_code == 200
    ids = [p["id"] for p in client.get("/api/programme?day=2027-06-13").json()]
    assert "le-kiosque-2027-06-13-1100" in ids
    # "restart the server": a fresh read of the file still has it
    assert JsonStorage(data_file).load().performance("le-kiosque-2027-06-13-1100")


def test_busy_venue_is_409(client):
    client.post("/api/performances", json=SOLO)
    response = client.post(
        "/api/performances",
        json={**SOLO, "start": "2027-06-13T11:30", "artist": "tom-vasseur"},
    )
    assert response.status_code == 409
    assert "Le Kiosque is busy" in response.json()["detail"]


def test_artist_on_stage_elsewhere_is_409(client):
    client.post("/api/performances", json=SOLO)
    response = client.post(
        "/api/performances",
        json={**SOLO, "venue": "grand-casino", "start": "2027-06-13T12:00"},
    )
    assert response.status_code == 409
    assert "Nora Lebrun is on stage" in response.json()["detail"]


def test_lineup_with_one_act_is_422(client):
    response = client.post(
        "/api/performances",
        json={
            "kind": "lineup",
            "title": "Soirée",
            "venue": "theatre-des-planches",
            "start": "2027-06-13T13:00",
            "duration_minutes": 60,
            "host": "paul-kerbrat",
            "acts": ["hugo-lemaire"],
        },
    )
    assert response.status_code == 422
    assert "at least 2 acts" in response.json()["detail"]


def test_lineup_with_two_acts_is_accepted(client):
    response = client.post(
        "/api/performances",
        json={
            "kind": "lineup",
            "title": "Soirée",
            "venue": "theatre-des-planches",
            "start": "2027-06-13T13:00",
            "duration_minutes": 60,
            "host": "paul-kerbrat",
            "acts": ["hugo-lemaire", "tom-vasseur"],
        },
    )
    assert response.status_code == 201


def test_move_changes_the_identity(client, data_file):
    client.post("/api/performances", json=SOLO)
    response = client.put(
        "/api/performances/le-kiosque-2027-06-13-1100",
        json={**SOLO, "start": "2027-06-13T12:00"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == "le-kiosque-2027-06-13-1200"
    assert client.get("/api/performances/le-kiosque-2027-06-13-1100").status_code == 404
    assert JsonStorage(data_file).load().performance("le-kiosque-2027-06-13-1200")


def test_refused_move_leaves_everything_as_it_was(client, data_file):
    client.post("/api/performances", json=SOLO)
    before = data_file.read_bytes()
    response = client.put(
        "/api/performances/le-kiosque-2027-06-13-1100",
        json={**SOLO, "start": "2027-06-13T15:00"},
    )
    assert response.status_code == 409  # Maya Choukri's show fills Le Kiosque at 15:00
    assert (
        client.get("/api/performances/le-kiosque-2027-06-13-1100").json()["start"]
        == "2027-06-13T11:00"
    )
    assert data_file.read_bytes() == before


def test_register_twice_the_same_name(client, data_file):
    url = f"/api/performances/{STAND_UP_LAB}/participants"
    first = client.post(url, json={"name": "Camille Roy"})
    assert first.status_code == 201
    assert first.json()["places_left"] == 5
    second = client.post(url, json={"name": "Camille Roy"})
    assert second.status_code == 409
    assert "already registered" in second.json()["detail"]
    saved = JsonStorage(data_file).load().performance(STAND_UP_LAB).participants
    assert saved.count("Camille Roy") == 1


def test_full_workshop_is_409(client):
    client.post(
        "/api/performances",
        json={
            "kind": "workshop",
            "title": "Tiny Lab",
            "venue": "la-cabane",
            "start": "2027-06-12T14:00",
            "duration_minutes": 60,
            "teacher": "ines-moreau",
            "max_participants": 1,
        },
    )
    url = "/api/performances/la-cabane-2027-06-12-1400/participants"
    assert client.post(url, json={"name": "A One"}).status_code == 201
    response = client.post(url, json={"name": "B Two"})
    assert response.status_code == 409
    assert "is full" in response.json()["detail"]


def test_registering_for_a_solo_is_422(client):
    response = client.post(
        f"/api/performances/{MAYA_SOLO}/participants", json={"name": "Camille Roy"}
    )
    assert response.status_code == 422


def test_add_artist_then_the_same_without_accent_or_case(client, data_file):
    first = client.post("/api/artists", json={"name": "Zoé Tanguy"})
    assert first.status_code == 201
    assert first.json()["slug"] == "zoe-tanguy"
    second = client.post("/api/artists", json={"name": "zoe tanguy"})
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]
    assert JsonStorage(data_file).load().artist("zoe-tanguy")
    assert "zoe-tanguy" in [a["slug"] for a in client.get("/api/artists").json()]


def test_cancel_is_204_without_body_then_404(client, data_file):
    response = client.delete(f"/api/performances/{MAYA_SOLO}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.delete(f"/api/performances/{MAYA_SOLO}").status_code == 404
    assert MAYA_SOLO not in [p.id for p in JsonStorage(data_file).load().performances]


def test_wrong_shapes_are_422(client):
    missing = {k: v for k, v in SOLO.items() if k != "title"}
    assert client.post("/api/performances", json=missing).status_code == 422
    assert (
        client.post("/api/performances", json={**SOLO, "kind": "circus"}).status_code
        == 422
    )
    assert (
        client.post("/api/performances", json={**SOLO, "extra": 1}).status_code == 422
    )
    assert (
        client.post(
            "/api/performances", json={**SOLO, "duration_minutes": "long"}
        ).status_code
        == 422
    )
    assert client.post("/api/artists", json={}).status_code == 422


def test_domain_invalid_values_are_422(client):
    assert (
        client.post(
            "/api/performances", json={**SOLO, "duration_minutes": 0}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/performances", json={**SOLO, "start": "2027-07-01T11:00"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/performances", json={**SOLO, "start": "2027-06-13T11:00+02:00"}
        ).status_code
        == 422
    )


def test_unknown_venue_or_artist_is_404(client):
    assert (
        client.post("/api/performances", json={**SOLO, "venue": "nowhere"}).status_code
        == 404
    )
    assert (
        client.post("/api/performances", json={**SOLO, "artist": "nobody"}).status_code
        == 404
    )


def test_read_routes_keep_their_statuses(client):
    assert client.get("/api/artists/nobody").status_code == 404
    assert client.get("/api/programme?day=2030-01-01").status_code == 422
    assert client.get("/api/programme?venue=nowhere").status_code == 404
    assert client.get("/api/programme?day=2027-06-13").status_code == 200


def test_damaged_data_file_is_500(client, data_file):
    data_file.write_text("{ not json")
    response = client.get("/api/festival")
    assert response.status_code == 500
    assert "damaged" in response.json()["detail"]


def test_workshop_put_with_participants_like_the_admin_page_sends(client, data_file):
    body = {
        "kind": "workshop",
        "title": "Stand-up Lab",
        "venue": "la-cabane",
        "start": "2027-06-12T14:00",
        "duration_minutes": 120,
        "description": "",
        "teacher": "paul-kerbrat",
        "max_participants": 10,
        "participants": ["Chloé D.", "Nathan P.", "Inès T.", "Hugo S."],
    }
    response = client.put(f"/api/performances/{STAND_UP_LAB}", json=body)
    assert response.status_code == 200
    assert response.json()["id"] == "la-cabane-2027-06-12-1400"
    assert response.json()["places_left"] == 6


def test_workshop_put_without_participants_keeps_them(client):
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
    assert len(response.json()["participants"]) == 4


def test_workshop_put_with_too_many_participants_is_422(client):
    body = {
        "kind": "workshop",
        "title": "Stand-up Lab",
        "venue": "la-cabane",
        "start": "2027-06-12T10:30",
        "duration_minutes": 120,
        "teacher": "paul-kerbrat",
        "max_participants": 2,
        "participants": ["A One", "B Two", "C Three"],
    }
    assert client.put(f"/api/performances/{STAND_UP_LAB}", json=body).status_code == 422


def test_admin_is_served_before_the_site(client):
    admin = client.get("/admin/")
    assert admin.status_code == 200
    assert "Admin - Deauville" in admin.text
    assert client.get("/admin/admin.js").status_code == 200
    assert client.get("/admin/admin.css").status_code == 200
    site = client.get("/")
    assert site.status_code == 200
    assert "Admin - Deauville" not in site.text
