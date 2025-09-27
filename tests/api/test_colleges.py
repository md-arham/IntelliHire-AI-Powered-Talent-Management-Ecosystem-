import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app  # Update the import path as per your actual main.py
from app.database.db import Base, get_db
from app.schemas.colleges_schemas import CollegeCreate, CollegeUpdate
from uuid import uuid4

# Set up an in-memory SQLite test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the dependency
@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = lambda: TestingSessionLocal()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def sample_college(client):
    college_data = {
        "name": "Test College",
        "location": "Test City",
        "affiliated_university": "Test University"
    }
    response = client.post("/colleges/", json=college_data)
    assert response.status_code == 201
    return response.json()

def test_create_college(client):
    data = {
        "name": "New College",
        "location": "New City",
        "affiliated_university": "New University"
    }
    response = client.post("/colleges/", json=data)
    assert response.status_code == 201
    assert response.json()["name"] == "New College"

def test_get_colleges(client, sample_college):
    response = client.get("/colleges/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert any(c["name"] == "Test College" for c in response.json())

def test_get_college_by_id(client, sample_college):
    college_id = sample_college["college_id"]
    response = client.get(f"/colleges/{college_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Test College"

def test_update_college(client, sample_college):
    college_id = sample_college["college_id"]
    update_data = {
        "name": "Updated College",
        "location": "Updated City",
        "affiliated_university": "Updated University"
    }
    response = client.put(f"/colleges/{college_id}", json=update_data)
    assert response.status_code == 200
    assert response.json()["name"] == "Updated College"

def test_delete_college(client, sample_college):
    college_id = sample_college["college_id"]
    response = client.delete(f"/colleges/{college_id}")
    assert response.status_code == 200
    # Verify it's deleted
    get_response = client.get(f"/colleges/{college_id}")
    assert get_response.status_code == 404
