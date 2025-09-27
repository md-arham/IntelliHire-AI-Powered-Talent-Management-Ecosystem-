
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from internHire import app
from app.database.db import Base, get_db
from tests.test_settings import test_settings  # import your new test settings here
from app.utils.settings import settings  # original settings

# Use the test DB URL from test_settings
TEST_DB_URL = test_settings.DB_URL

engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

@pytest.fixture(scope="function")
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Temporarily swap global settings with test settings for the duration of the test client
    original_settings_dict = settings.model_dump()
    for key, val in test_settings.test_settings.model_dump().items():
        setattr(settings, key, val)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()

    # Restore original settings after test
    for key, val in original_settings_dict.items():
        setattr(settings, key, val)
