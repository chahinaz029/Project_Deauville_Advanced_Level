"""The command line: it receives a storage, catches the whole error family."""

import deauville.main as cli
import pytest


def test_programme_prints_the_day(memory_storage, capsys):
    cli.main(["programme", "2027-06-13"], storage=memory_storage)
    out = capsys.readouterr().out
    assert "Programme for Sunday 13 June:" in out
    assert "15:00-16:00 | Le Kiosque | First Time Here (solo)" in out


def test_summary_without_a_command(memory_storage, capsys):
    cli.main([], storage=memory_storage)
    out = capsys.readouterr().out
    assert "Deauville Festival du Rire 2027" in out
    assert "Performances: 23" in out


def test_venues_artist_and_now(memory_storage, capsys):
    cli.main(["venues"], storage=memory_storage)
    assert "le-kiosque | Le Kiosque (120 seats)" in capsys.readouterr().out
    cli.main(["artist", "maya-choukri"], storage=memory_storage)
    assert "First Time Here" in capsys.readouterr().out
    cli.main(["now", "2027-06-13T15:30"], storage=memory_storage)
    assert "First Time Here at Le Kiosque, until 16:00" in capsys.readouterr().out


def test_unknown_artist_prints_an_error_and_exits_1(memory_storage, capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["artist", "nobody"], storage=memory_storage)
    assert stop.value.code == 1
    assert "Error: No artist 'nobody'." in capsys.readouterr().out


def test_bad_day_is_an_error_not_a_crash(memory_storage, capsys):
    with pytest.raises(SystemExit):
        cli.main(["programme", "tomorrow"], storage=memory_storage)
    assert "use YYYY-MM-DD" in capsys.readouterr().out


def test_data_option_uses_another_file_before_or_after_the_command(data_file, capsys):
    cli.main(["--data", str(data_file), "programme", "2027-06-13"])
    first = capsys.readouterr().out
    cli.main(["programme", "2027-06-13", "--data", str(data_file)])
    assert capsys.readouterr().out == first
    assert "First Time Here" in first


def test_missing_data_file_is_a_clear_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["--data", str(tmp_path / "nope.json")])
    assert stop.value.code == 1
    assert "was not found" in capsys.readouterr().out


def test_cancel_saves_to_the_storage(memory_storage, capsys):
    cli.main(["cancel", "le-kiosque-2027-06-13-1500"], storage=memory_storage)
    assert "Cancelled: First Time Here" in capsys.readouterr().out
    ids = [p.id for p in memory_storage.load().performances]
    assert "le-kiosque-2027-06-13-1500" not in ids


def test_cancel_unknown_id(memory_storage, capsys):
    with pytest.raises(SystemExit):
        cli.main(["cancel", "nope"], storage=memory_storage)
    assert "Error: No performance 'nope'." in capsys.readouterr().out


def answers(monkeypatch, *values):
    replies = iter(values)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(replies))


def test_add_saves_and_refuses_a_conflict(memory_storage, monkeypatch, capsys):
    answers(
        monkeypatch,
        "Nora en solo",
        "nora-lebrun",
        "le-kiosque",
        "2027-06-13T11:00",
        "45",
    )
    cli.main(["add"], storage=memory_storage)
    assert "Added: le-kiosque-2027-06-13-1100" in capsys.readouterr().out
    assert memory_storage.load().performance("le-kiosque-2027-06-13-1100")

    answers(monkeypatch, "Again", "tom-vasseur", "le-kiosque", "2027-06-13T11:30", "45")
    with pytest.raises(SystemExit):
        cli.main(["add"], storage=memory_storage)
    assert "Le Kiosque is busy" in capsys.readouterr().out


def test_add_with_a_bad_number_is_an_error(memory_storage, monkeypatch, capsys):
    answers(monkeypatch, "X", "nora-lebrun", "le-kiosque", "2027-06-13T11:00", "long")
    with pytest.raises(SystemExit):
        cli.main(["add"], storage=memory_storage)
    assert "is not a number of minutes" in capsys.readouterr().out


def test_serve_starts_uvicorn_with_the_chosen_storage(memory_storage, monkeypatch):
    uvicorn = pytest.importorskip("uvicorn")
    pytest.importorskip("fastapi")
    started = {}
    monkeypatch.setattr(
        uvicorn, "run", lambda app, **options: started.update(app=app, **options)
    )
    cli.main(["serve", "--port", "8123"], storage=memory_storage)
    assert started["port"] == 8123 and started["host"] == "127.0.0.1"
    assert started["app"].title == "Festival API"
