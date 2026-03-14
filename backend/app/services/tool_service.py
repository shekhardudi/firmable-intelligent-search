"""
Tool Service for Agentic Search.

Uses the OpenAI LLM to identify company names relevant to a time-sensitive
query (funding, news, events), then resolves them with a fuzzy lookup in
OpenSearch.  No extra dependencies required beyond what is already installed.

Optional Tavily integration: if TAVILY_API_KEY is set in the environment,
the service will use Tavily web-search for more up-to-date results before
falling back to the LLM knowledge base.
"""
import json
import os
import structlog
from typing import Any
from openai import OpenAI

logger = structlog.get_logger(__name__)


class ToolService:
    """
    Resolves agentic queries by:
    1. Asking the LLM to name companies that match the query.
    2. Fuzzy-matching those names against OpenSearch.
    """

    def __init__(self, opensearch_service, api_key: str, model: str = "gpt-4o-mini"):
        self.opensearch = opensearch_service
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self._tavily_key: str | None = os.getenv("TAVILY_API_KEY")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def call(self, data_type: str, query: str) -> list[dict[str, Any]]:
        """
        Entry point called by AgenticSearchStrategy.
        Returns a list of OpenSearch source dicts (_source + _id + _score).
        """
        names = self._extract_company_names(query, data_type)
        logger.info(
            "agentic_companies_identified",
            data_type=data_type,
            count=len(names),
            sample=names[:5],
        )
        return self._resolve_companies(names)

    # ------------------------------------------------------------------
    # Step 1 – identify company names
    # ------------------------------------------------------------------

    def _extract_company_names(self, query: str, data_type: str) -> list[str]:
        """
        Ask the LLM to list up to 20 company names relevant to the query.
        Optionally enrich with Tavily web search first.
        """
        context_snippet = ""

        # Optional: use Tavily to get fresh web context
        if self._tavily_key:
            try:
                context_snippet = self._tavily_search(query)
            except Exception as e:
                logger.warning("tavily_search_failed", error=str(e))

        prompt = (
            f"You are a business intelligence assistant. "
            f"The user is looking for companies that match this query: '{query}'\n"
        )
        if context_snippet:
            prompt += f"\nRecent web context:\n{context_snippet}\n"

        prompt += (
            "\nList up to 20 real company names that best match this query. "
            "Return ONLY a JSON array of company name strings, nothing else. "
            'Example: ["Company A", "Company B"]'
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0,
            )
            content = response.choices[0].message.content.strip()
            # Strip markdown code fences if present
            if content.startswith("```"):
                parts = content.split("```")
                content = parts[1].lstrip("json").strip() if len(parts) > 1 else content
            names: list[str] = json.loads(content)
            return [n.strip() for n in names if isinstance(n, str)]
        except Exception as e:
            logger.error("llm_company_extraction_failed", error=str(e))
            return []

    # ------------------------------------------------------------------
    # Step 2 – resolve names to OpenSearch documents
    # ------------------------------------------------------------------

    def _resolve_companies(self, names: list[str]) -> list[dict[str, Any]]:
        """
        Fuzzy-match each name against OpenSearch name/domain fields.
        Deduplicates by document ID and filters low-confidence matches.
        """
        if not names:
            return []

        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for name in names:
            try:
                resp = self.opensearch.search(
                    index="companies",
                    query={
                        "multi_match": {
                            "query": name,
                            "fields": ["name^3", "domain"],
                            "type": "best_fields",
                            "fuzziness": "AUTO",
                        }
                    },
                    size=2,
                )
                for hit in resp.get("hits", {}).get("hits", []):
                    doc_id = hit.get("_id")
                    score = float(hit.get("_score", 0))
                    # Require a minimum score to avoid false matches
                    if doc_id not in seen_ids and score > 1.0:
                        seen_ids.add(doc_id)
                        results.append(
                            {**hit["_source"], "_id": doc_id, "_score": score}
                        )
            except Exception as e:
                logger.warning("company_resolution_failed", name=name, error=str(e))

        return results

    # ------------------------------------------------------------------
    # Optional Tavily integration
    # ------------------------------------------------------------------

    def _tavily_search(self, query: str) -> str:
        """
        Use Tavily Search API for real-time web results.
        Returns a plain-text summary snippet.
        """
        import requests  # already in requirements.txt

        resp = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": self._tavily_key, "query": query, "max_results": 5},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        snippets = [r.get("content", "") for r in data.get("results", [])]
        return "\n".join(snippets[:3])
