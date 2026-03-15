"""
Tests for SearchOrchestrator.

Verifies that the orchestrator correctly routes queries to strategies
and builds the expected response shape.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.services.intent_classifier import QueryIntent, SearchIntent
from app.services.search_strategies import SearchResult


def _make_intent(category: str = "regular", confidence: float = 0.95) -> QueryIntent:
    return QueryIntent(
        category=SearchIntent(category),
        confidence=confidence,
        filters={},
        search_query="test query",
        needs_external_data=False,
        field_boosts={},
        reasoning="test",
    )


def _make_search_result() -> SearchResult:
    return SearchResult(
        company_id="c1",
        company_name="Acme Corp",
        domain="acme.com",
        industry="technology",
        country="US",
        locality="San Francisco",
        relevance_score=0.9,
        search_method="bm25",
        ranking_source="bm25",
        matching_reason="name match",
        year_founded=2010,
        size_range="51-200",
        current_employee_estimate=100,
    )


@pytest.fixture
def orchestrator():
    with patch("app.services.orchestrator.get_intent_classifier") as mock_cls, \
         patch("app.services.orchestrator.RegularSearchStrategy") as mock_reg, \
         patch("app.services.orchestrator.SemanticSearchStrategy") as mock_sem, \
         patch("app.services.orchestrator.AgenticSearchStrategy") as mock_age:

        mock_classifier = MagicMock()
        mock_cls.return_value = mock_classifier
        mock_classifier.classify.return_value = _make_intent("regular")

        for Strat in (mock_reg, mock_sem, mock_age):
            Strat.return_value.search.return_value = (
                [_make_search_result()],
                {"score_range": {"min": 0.5, "max": 1.0}},
            )

        from app.services.orchestrator import SearchOrchestrator
        orch = SearchOrchestrator.__new__(SearchOrchestrator)
        orch.classifier = mock_classifier
        orch.regular_strategy = mock_reg.return_value
        orch.semantic_strategy = mock_sem.return_value
        orch.agentic_strategy = mock_age.return_value
        yield orch, mock_classifier, mock_reg.return_value, mock_sem.return_value


def test_regular_query_routes_to_regular_strategy(orchestrator):
    orch, classifier, regular_strat, _ = orchestrator
    classifier.classify.return_value = _make_intent("regular")
    result = orch.search("Apple Inc", limit=10, page=1)
    regular_strat.search.assert_called_once()
    assert result.intent["category"] == "regular"


def test_semantic_query_routes_to_semantic_strategy(orchestrator):
    orch, classifier, _, semantic_strat = orchestrator
    classifier.classify.return_value = _make_intent("semantic", 0.88)
    result = orch.search("sustainable energy companies Europe", limit=10, page=1)
    semantic_strat.search.assert_called_once()
    assert result.intent["category"] == "semantic"


def test_response_has_required_fields(orchestrator):
    orch, classifier, _, _ = orchestrator
    classifier.classify.return_value = _make_intent("regular")
    result = orch.search("Apple", limit=5, page=1)
    assert hasattr(result, "results")
    assert hasattr(result, "intent")
    assert hasattr(result, "trace_id")
    assert hasattr(result, "metadata")


def test_results_respect_limit(orchestrator):
    """Orchestrator passes limit to strategy via SearchContext; strategy enforces it."""
    orch, classifier, regular_strat, _ = orchestrator
    classifier.classify.return_value = _make_intent("regular")
    regular_strat.search.return_value = (
        [_make_search_result()] * 10,
        {"score_range": {}},
    )
    result = orch.search("Apple", limit=10, page=1)
    # Verify the strategy was called with a context carrying the correct limit
    called_ctx = regular_strat.search.call_args[0][0]
    assert called_ctx.limit == 10
    assert len(result.results) == 10
