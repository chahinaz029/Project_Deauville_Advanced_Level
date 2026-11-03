"""A storage is a replaceable part: the file and the memory behave the same."""

import json
from datetime import datetime

import pytest
from deauville.festival import (
    DataFileError,
    Festival,
    JsonStorage,
    MemoryStorage,
    SoloShow,
    Storage,
)


def a_new_show(festival):
    return SoloShow(
        title="Nora",
        venue=festival.venue("le-kiosque"),
        start=datetime(2027, 6, 13, 11, 0),
        duration_minutes=45,
        artist=festival.artist("nora-lebrun"),
    )


def test_both_storages_fit_the_interface(storage, memory_storage):
    assert isinstance(storage, Storage)
    assert isinstance(memory_storage, Storage)
    with pytest.raises(TypeError):
        Storage()  # abstract: it only says what a storage must do


@pytest.mark.parametrize("which", ["storage", "memory_storage"])
def test_save_then_load_returns_the_change(which, request):
    chosen = request.getfixturevalue(which)
    festival = chosen.load()
    festival.add(a_new_show(festival))
    chosen.save(festival)
    assert chosen.load().performance("le-kiosque-2027-06-13-1100")


@pytest.mark.parametrize("which", ["storage", "memory_storage"])
def test_an_unsaved_change_is_not_kept(which, request):
    chosen = request.getfixturevalue(which)
    festival = chosen.load()
    festival.add(a_new_show(festival))  # never saved
    assert len(chosen.load().performances) == 23


def test_memory_storage_does_not_share_state_with_what_it_was_given(festival):
    memory = MemoryStorage(festival)
    festival.add(a_new_show(festival))
    assert len(memory.load().performances) == 23


def test_memory_storage_can_start_from_plain_data(data_file):
    data = json.loads(data_file.read_text(encoding="utf-8"))
    assert len(MemoryStorage(data).load().performances) == 23


def test_the_json_file_keeps_its_content_after_a_round_trip(storage, data_file):
    before = json.loads(data_file.read_text(encoding="utf-8"))
    storage.save(storage.load())
    assert json.loads(data_file.read_text(encoding="utf-8")) == before


def test_json_storage_errors_are_festival_errors(tmp_path):
    with pytest.raises(DataFileError, match="was not found"):
        JsonStorage(tmp_path / "nope.json").load()
    broken = tmp_path / "broken.json"
    broken.write_text("{ not json")
    with pytest.raises(DataFileError, match="damaged"):
        JsonStorage(broken).load()
    wrong = tmp_path / "wrong.json"
    wrong.write_text('{"name": "x"}')
    with pytest.raises(DataFileError, match="invalid structure"):
        JsonStorage(wrong).load()


def test_a_rule_broken_in_the_file_is_a_data_error(data_file):
    data = json.loads(data_file.read_text(encoding="utf-8"))
    lineup = next(p for p in data["performances"] if p["kind"] == "lineup")
    lineup["acts"] = lineup["acts"][:1]
    data_file.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DataFileError, match="at least 2 acts"):
        JsonStorage(data_file).load()


def test_save_leaves_no_temporary_file(storage, data_file):
    storage.save(storage.load())
    assert not data_file.with_name("festival.json.tmp").exists()


def test_the_festival_knows_nothing_about_files():
    assert not hasattr(Festival, "from_file")
    assert not hasattr(Festival, "save")
    assert not hasattr(Festival, "storage_path")
