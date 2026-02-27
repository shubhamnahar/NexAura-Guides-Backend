import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Mock environment variables
os.environ["SECRET_KEY"] = "test_secret_key"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.main import app
from app.database import Base, get_db
from app import models, auth

# Setup test database
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db_session(setup_db):
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()

def test_public_search_filters_private_guides(client):
    # 1. Create a user
    email = "test@example.com"
    password = "password123"
    reg_resp = client.post("/api/auth/register", json={"email": email, "password": password})
    assert reg_resp.status_code == 201

    # 2. Get a token
    tok_resp = client.post("/api/auth/token", data={"username": email, "password": password})
    assert tok_resp.status_code == 200
    token = tok_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Create a public guide
    pub_resp = client.post(
        "/api/guides/",
        json={
            "name": "Public Guide",
            "shortcut": "pub",
            "description": "Public",
            "is_public": True,
            "steps": [{"instruction": "Step 1", "selector": "body"}]
        },
        headers=headers
    )
    assert pub_resp.status_code == 201

    # 4. Create a private guide
    priv_resp = client.post(
        "/api/guides/",
        json={
            "name": "Private Guide",
            "shortcut": "priv",
            "description": "Private",
            "is_public": False,
            "steps": [{"instruction": "Step 1", "selector": "body"}]
        },
        headers=headers
    )
    assert priv_resp.status_code == 201

    # 5. Search public guides
    search_resp = client.get("/api/guides/public")
    assert search_resp.status_code == 200
    guides = search_resp.json()

    # 6. Assert only public guide is returned
    assert len(guides) == 1
    assert guides[0]["name"] == "Public Guide"
    assert guides[0]["is_public"] is True

def test_public_search_with_term_filters_private_guides(client):
    # 1. Create a user
    email = "test2@example.com"
    password = "password123"
    client.post("/api/auth/register", json={"email": email, "password": password})

    # 2. Get a token
    tok_resp = client.post("/api/auth/token", data={"username": email, "password": password})
    token = tok_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Create a public guide
    client.post(
        "/api/guides/",
        json={
            "name": "FindMe Public",
            "shortcut": "find1",
            "description": "Searchable",
            "is_public": True,
            "steps": [{"instruction": "Step 1", "selector": "body"}]
        },
        headers=headers
    )

    # 4. Create a private guide with same search term
    client.post(
        "/api/guides/",
        json={
            "name": "FindMe Private",
            "shortcut": "find2",
            "description": "Hidden",
            "is_public": False,
            "steps": [{"instruction": "Step 1", "selector": "body"}]
        },
        headers=headers
    )

    # 5. Search with term
    search_resp = client.get("/api/guides/public?search=FindMe")
    assert search_resp.status_code == 200
    guides = search_resp.json()

    # 6. Assert only public guide is returned
    assert len(guides) == 1
    assert guides[0]["name"] == "FindMe Public"
