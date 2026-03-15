"""Integration-style tests for the /api/search/intelligent endpoint."""
import pytest
from unittest.mock import MagicMock, patch

from app.services.intent_classifier import QueryIntent, SearchIntent


def _intent(category: str = "regular") -> QueryIntent:
    return QueryIntent(
        category=SearchIntent(category),
        confidence=0.95,
        filters={},
        search_query="test",
        needs_external_data=False,
        field_boosts={},
        reasoning="test",
    )


def _orch_response(query: str, category: str = "regular"):
    """Build a minimal OrchestratorResponse-shaped object."""
    resp = MagicMock()
    resp.results = [
        {
            "id": "c1",
            "name": "Acme Corp",
            "domain": "acme.com",
            "industry": "technology",
            "country": "US",
            "locality": "San Francisco",
            "relevance_score": 0.9,
            "search_method": "bm25",
            "ranking_source": "bm25",
            "matching_reason": "name match",
            "year_founded": 2010,
            "size_range": "51-200",
            "current_employee_estimate": 100,
        }
    ]
    resp.trace_id = "trace-001"
    resp.intent = {"category": category, "confidence": 0.95, "filters": {}, "search_query": query}
    resp.metadata = {
        "response_time_ms": 42,
        "search_execution": {"score_range": {"min": 0.5, "max": 1.0}},
    }
    resp.response_headers = {
        "X-Search-Logic": category,
        "X-Confidence": "0.95",
        "X-Response-Time-MS": "42",
        "X-Total-Results": "1",
    }
    return resp


@pytest.fixture
def patched_orchestrator():
    with patch("app.api.routes.get_search_orchestrator") as mock_get:
        orch = MagicMock()
        orch.search.return_value = _orch_response("Apple Inc")
        mock_get.return_value = orch
        yield orch


def test_intelligent_search_success(test_client, patched_orchestrator):
    resp = test_client.post(
        "/api/search/intelligent",
        json={"query": "Apple Inc", "limit": 10, "page": 1},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["results"]) == 1
    assert data["results"][0]["name"] == "Acme Corp"


def test_intelligent_search_returns_metadata(test_client, patched_orchestrator):
    resp = test_client.post(
        "/api/search/intelligent",
        json={"query": "tech startups", "limit": 5},
    )
    assert resp.status_code == 200
    meta = resp.json()["metadata"]
    assert "trace_id" in meta
    assert "response_time_ms" in meta


def test_intelligent_search_with_filters(test_client, patched_orchestrator):
    resp = test_client.post(
        "/api/search/intelligent",
        json={
            "query": "tech companies",
            "limit": 10,
            "filters": {"country": "US", "industry": "technology"},
        },
    )
    assert resp.status_code == 200


def test_intelligent_search_query_too_short(test_client):
    resp = test_client.post(
        "/api/search/intelligent",
        json={"query": "", "limit": 10},
    )
    assert resp.status_code == 422  # Pydantic validation error


def test_intelligent_search_query_too_long(test_client):
    resp = test_client.post(
        "/api/search/intelligent",
        json={"query": "x" * 501, "limit": 10},
    )
    assert resp.status_code == 422


def test_intelligent_search_limit_out_of_range(test_client):
    resp = test_client.post(
        "/api/search/intelligent",
        json={"query": "Apple", "limit": 0},
    )
    assert resp.status_code == 422


def test_health_endpoint(test_client):
    resp = test_client.get("/api/search/health")
    assert resp.status_code == 200
