import shutil

import pytest
from deauville.api import create_app
from deauville.festival import (
    ADMIN_DIR,
    DATA_FILE,
    PUBLIC_DIR,
    JsonStorage,
    MemoryStorage,
)
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def the_real_data_file_is_never_touched():
    """Whatever the tests do, data/festival.json must come out unchanged."""
    before = DATA_FILE.read_bytes()
    yield
    assert DATA_FILE.read_bytes() == before, "a test modified data/festival.json"


@pytest.fixture
def data_file(tmp_path):
    """A copy of the real file: tests never touch the original."""
    copy = tmp_path / "festival.json"
    shutil.copy(DATA_FILE, copy)
    return copy


@pytest.fixture
def storage(data_file):
    return JsonStorage(data_file)


@pytest.fixture
def festival(storage):
    return storage.load()


@pytest.fixture
def memory_storage(festival):
    return MemoryStorage(festival)


@pytest.fixture
def client(storage, tmp_path):
    # If web/public or web/admin are missing, empty folders let the app start.
    public = PUBLIC_DIR if PUBLIC_DIR.is_dir() else tmp_path / "public"
    admin = ADMIN_DIR if ADMIN_DIR.is_dir() else tmp_path / "admin"
    public.mkdir(exist_ok=True)
    admin.mkdir(exist_ok=True)
    return TestClient(create_app(storage, public_dir=public, admin_dir=admin))
