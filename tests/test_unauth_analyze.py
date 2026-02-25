import pytest
from fastapi.testclient import TestClient
import os

# Set environment variables for testing
os.environ["SECRET_KEY"] = "test_secret_key"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.main import app

client = TestClient(app)

def test_analyze_unauthenticated():
    # This should now return 401 Unauthorized
    response = client.post("/api/analyze/analyze", files={"file": ("test.png", b"fake image data", "image/png")}, data={"question": "What is this?"})
    assert response.status_code == 401

def test_analyze_live_unauthenticated():
    # This should now return 401 Unauthorized
    response = client.post("/api/analyze/analyze_live", json={"image_base64": "data:image/png;base64,ZmFrZQ==", "question": "What is this?"})
    assert response.status_code == 401
