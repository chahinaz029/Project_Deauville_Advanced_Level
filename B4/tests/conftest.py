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


@pytest.fixture
def data_file(tmp_path):
    """Une copie du vrai fichier : les tests ne touchent jamais à l'original."""
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
    # Si web/public ou web/admin n'existent pas, on met des dossiers vides
    # pour que l'application démarre (seul le test de l'admin en a besoin).
    public = PUBLIC_DIR if PUBLIC_DIR.is_dir() else tmp_path / "public"
    admin = ADMIN_DIR if ADMIN_DIR.is_dir() else tmp_path / "admin"
    public.mkdir(exist_ok=True)
    admin.mkdir(exist_ok=True)
    return TestClient(create_app(storage, public_dir=public, admin_dir=admin))
