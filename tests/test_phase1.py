"""
Phase 1 tests — verify the app starts and models validate correctly.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.api.main import app
from app.models.claim import ExtractedField, ExtractionSource, OEM


client = TestClient(app)


def test_health_check_returns_200():
    with patch("boto3.client") as mock_boto:
        mock_client = MagicMock()
        mock_boto.return_value = mock_client
        response = client.get("/health/", headers={"X-API-Key": "dev-key-change-in-prod"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"


def test_valid_vin_passes_validation():
    field = ExtractedField(
        value="1FTFW1ET5DKE12345",
        source=ExtractionSource.TEXTRACT,
        confidence=0.99,
    )
    assert field.value == "1FTFW1ET5DKE12345"


def test_invalid_vin_raises_error():
    from app.models.claim import ExtractedClaim
    import pytest
    with pytest.raises(Exception):
        ExtractedField(
            value="INVALID",
            source=ExtractionSource.TEXTRACT,
            confidence=0.5,
        )
