import os
import pytest
from fastapi.testclient import TestClient

# Mock environment variables
os.environ["SECRET_KEY"] = "test_secret_key"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.main import app

client = TestClient(app)

def test_analyze_is_protected():
    # Now it SHOULD return 401 Unauthorized if no token is provided
    response = client.post("/api/analyze/analyze", data={"question": "What is this?"}, files={"file": ("test.png", b"fake image content", "image/png")})
    assert response.status_code == 401, "Endpoint /api/analyze/analyze should be protected"

def test_analyze_live_is_protected():
    # Now it SHOULD return 401 Unauthorized if no token is provided
    response = client.post("/api/analyze/analyze_live", json={"image_base64": "data:image/png;base64,ZmFrZQ==", "question": "test"})
    assert response.status_code == 401, "Endpoint /api/analyze/analyze_live should be protected"
