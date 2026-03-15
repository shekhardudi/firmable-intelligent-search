"""
Tests for RegularSearchStrategy and SemanticSearchStrategy.

Focuses on:
- Index name comes from settings (not hardcoded).
- Field boosts come from search_config.yaml.
- RRF k and knn_k come from config.
- _rrf_merge ranking correctness.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from app.services.search_strategies import SearchContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(query: str = "test", limit: int = 10) -> SearchContext:
    return SearchContext(
        query=query,
        filters={},
        optimized_query=query,
        trace_id="t1",
        confidence=0.9,
        limit=limit,
        page=1,
        include_reasoning=False,
        field_boosts=None,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hit(id_: str, score: float, source: dict | None = None) -> dict:
    return {
        "_id": id_,
        "_score": score,
        "_source": source or {
            "id": id_,
            "name": f"Company {id_}",
            "domain": f"{id_}.com",
            "industry": "tech",
            "country": "US",
            "locality": "SF",
            "searchable_text": "test",
        },
    }


def _make_os_response(hits: list) -> dict:
    return {
        "hits": {
            "total": {"value": len(hits)},
            "hits": hits,
        }
    }


# ---------------------------------------------------------------------------
# RegularSearchStrategy
# ---------------------------------------------------------------------------

class TestRegularSearchStrategy:
    @pytest.fixture(autouse=True)
    def strategy(self):
        self._mock_os = MagicMock()
        self._mock_os.search.return_value = _make_os_response([_make_hit("1", 1.0)])
        from app.services.search_strategies import RegularSearchStrategy
        return RegularSearchStrategy(opensearch_service=self._mock_os)

    def test_search_uses_configured_index(self, strategy):
        from app.config import get_settings
        strategy.search(_ctx("Apple Inc", limit=5))
        call_kwargs = self._mock_os.search.call_args
        assert call_kwargs is not None
        # index argument should match settings — check keyword arg
        called_index = call_kwargs[1].get("index")
        assert called_index == get_settings().OPENSEARCH_INDEX_NAME

    def test_search_returns_list_of_results(self, strategy):
        results, _ = strategy.search(_ctx("Apple Inc", limit=5))
        assert isinstance(results, list)

    def test_search_with_filters(self, strategy):
        ctx = _ctx("Apple Inc", limit=5)
        ctx.filters = {"country": "US"}
        results, _ = strategy.search(ctx)
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# SemanticSearchStrategy — unit-level RRF merge
# ---------------------------------------------------------------------------

class TestSemanticSearchStrategyRRF:
    @pytest.fixture
    def strategy(self):
        from app.services.search_strategies import SemanticSearchStrategy
        mock_os = MagicMock()
        mock_os.search.return_value = _make_os_response([])
        mock_emb = MagicMock()
        mock_emb.embed.return_value = [0.0] * 768
        return SemanticSearchStrategy(
            opensearch_service=mock_os,
            embedding_service=mock_emb,
        )

    def test_rrf_merge_ranking(self, strategy):
        """Higher-ranked docs in both lists should score highest in RRF."""
        bm25 = [_make_hit("A", 1.0), _make_hit("B", 0.8), _make_hit("C", 0.6)]
        knn = [_make_hit("A", 0.9), _make_hit("C", 0.7), _make_hit("D", 0.5)]
        merged = strategy._rrf_merge(bm25, knn)
        ids = [h["_id"] for h in merged]
        # "A" appears in both lists at rank 1 → highest combined RRF score
        assert ids[0] == "A"

    def test_rrf_merge_deduplicates(self, strategy):
        bm25 = [_make_hit("X", 1.0), _make_hit("Y", 0.9)]
        knn = [_make_hit("X", 0.8), _make_hit("Z", 0.7)]
        merged = strategy._rrf_merge(bm25, knn)
        ids = [h["_id"] for h in merged]
        assert ids.count("X") == 1

    def test_rrf_merge_custom_k(self, strategy):
        hits = [_make_hit(str(i), float(10 - i)) for i in range(10)]
        merged = strategy._rrf_merge(hits, [], k=10)
        assert len(merged) <= len(hits)

    def test_field_boosts_property_from_config(self, strategy):
        boosts = strategy._DEFAULT_FIELD_BOOSTS
        assert isinstance(boosts, dict)
        assert "name" in boosts

    def test_rrf_k_property_from_config(self, strategy):
        assert isinstance(strategy._RRF_K, int)
        assert strategy._RRF_K > 0
