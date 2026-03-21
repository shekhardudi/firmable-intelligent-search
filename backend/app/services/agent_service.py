"""
LangChain tool-calling agent for agentic search.

Architecture:
  - 3 tools:  web_search_company_events, lookup_companies_by_name, submit_final_results
  - The agent chooses tools based on the query, reasons over results, then calls
    submit_final_results to emit a validated JSON array.
  - Model is fully configurable via search_config.yaml  agentic.model
    (gpt-4o-mini, gpt-4o, gpt-4-turbo or any OpenAI tool-calling model).

Pydantic boundary models validate all external data:
  - TavilyResult     — each item from the Tavily Search API
  - CompanyEvent     — each item extracted from web results by the LLM
  - EventExtractionResponse — the full LLM extraction output
  - EnrichedCompanyDoc — the final output shape per company
  - *Input models    — typed args_schema for each StructuredTool

Prompts are loaded from app/prompts/:
  - agent_system.txt      — agent system prompt (guardrails, PII rules, tool descriptions)
  - agent_extraction.txt  — event extraction system prompt
"""

import hashlib
import json
import time
import structlog
from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field
from openai import OpenAI

from app.config import get_settings, get_search_config
from app.services.search_strategies import EventData
from app.services.pii_service import detect_pii
from app.services.prompt_loader import load_prompt

logger = structlog.get_logger(__name__)

# ── Prompts loaded from disk ──────────────────────────────────────────────────

# Loaded once at import time. The extraction prompt does not need today's date
# injected (each call adds it in the user message). The system prompt uses
# {today} which is .format()-ed at agent construction time.
_EXTRACTION_SYSTEM_PROMPT: str = load_prompt("agent_extraction.txt")
_LINKEDIN_EXTRACTION_PROMPT: str = load_prompt("agent_linkedin_extraction.txt")
_SYSTEM_PROMPT_TEMPLATE: str = load_prompt("agent_system.txt")

# ── Pydantic models for external data boundaries ─────────────────────────────


class TavilyResult(BaseModel):
    """Validated Tavily Search API result item."""
    title: str = ""
    url: str = ""
    content: str = ""
    published_date: Optional[str] = ""

    model_config = {"extra": "ignore", "coerce_numbers_to_str": True}


class CompanyEvent(BaseModel):
    """Structured company event extracted from web search by the LLM."""
    company_name: str
    event_type: Literal[
        "funding", "acquisition", "ipo", "merger", "partnership",
        "product_launch", "expansion", "layoffs", "other"
    ]
    amount: Optional[str] = None
    round: Optional[str] = None
    date: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    summary: str = ""
    source_url: Optional[str] = None

    model_config = {"extra": "ignore"}


class EventExtractionResponse(BaseModel):
    """Full validated LLM extraction output."""
    events: list[CompanyEvent] = []


class LinkedInProfile(BaseModel):
    """Structured company profile extracted from LinkedIn page."""
    description: Optional[str] = None
    headquarters: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    specialties: list[str] = []
    founded_year: Optional[int] = None
    website: Optional[str] = None
    recent_updates: Optional[str] = None

    model_config = {"extra": "ignore"}


class EnrichedCompanyDoc(BaseModel):
    """Final typed output per company — the shape submit_final_results produces."""
    id: str
    name: str
    domain: str = ""
    industry: str = ""
    country: str = ""
    locality: str = ""
    score: float = 1.0
    event_data: Optional[EventData] = None
    linkedin_profile: Optional[dict] = None

    model_config = {"extra": "ignore"}


# ── Tool input schemas ────────────────────────────────────────────────────────


class WebSearchInput(BaseModel):
    query: str = Field(..., description="Web search query for recent company events")


class LookupNamesInput(BaseModel):
    company_names: str = Field(
        ...,
        description="Comma-separated list of company names to look up in the database",
    )


class LinkedInLookupInput(BaseModel):
    company_name: str = Field(
        ...,
        description="Name of the company to look up on LinkedIn",
    )


class SubmitResultsInput(BaseModel):
    results_json: str = Field(
        default="[]",
        description="JSON array of company objects — the final answer. "
                    "Must be a JSON array, e.g. [] or [{\"id\": \"...\", \"name\": \"...\"}]",
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _recover_partial_events(raw: str) -> list[CompanyEvent]:
    """Try to salvage complete events from truncated JSON output."""
    import re
    events: list[CompanyEvent] = []
    # Find all complete JSON objects in the events array
    for m in re.finditer(r'\{[^{}]*"company_name"\s*:[^{}]+\}', raw):
        try:
            events.append(CompanyEvent.model_validate_json(m.group()))
        except Exception:
            continue
    return events


# ── AgentService ─────────────────────────────────────────────────────────────


class AgentService:
    """
    LangChain tool-calling agent for agentic company search.

    Model, max_iterations, and all thresholds are read from search_config.yaml
    agentic block so they can be changed without code edits.
    """

    def __init__(
        self,
        opensearch_service: Any,
        openai_api_key: str,
        model: str,
        tavily_key: Optional[str],
        max_iterations: int,
    ) -> None:
        _cfg = get_search_config().get("agentic", {})
        self._opensearch = opensearch_service
        self._tavily_key = tavily_key
        self._index = get_settings().OPENSEARCH_INDEX_NAME
        self._resolve_per_name: int = int(_cfg.get("resolve_per_name", 2))
        self._min_resolve_score: float = float(_cfg.get("min_resolve_score", 1.0))
        self._tavily_max_results: int = int(_cfg.get("tavily_max_results", 5))
        self._tavily_timeout_s: int = int(_cfg.get("tavily_timeout_s", 8))
        self._tavily_search_depth: str = str(_cfg.get("tavily_search_depth", "advanced"))
        self._llm_max_tokens: int = int(_cfg.get("llm_max_tokens", 800))
        self._resolve_to_index: bool = bool(_cfg.get("resolve_to_index", True))

        # Plain OpenAI client used for structured event extraction.
        # Short keepalive_expiry prevents stale connections after long idle.
        import httpx as _httpx
        self._openai = OpenAI(
            api_key=openai_api_key,
            http_client=_httpx.Client(
                limits=_httpx.Limits(keepalive_expiry=30),
                timeout=_httpx.Timeout(60.0, connect=5.0),
            ),
        )
        self._extraction_model = model

        # LangChain agent — imported here to keep startup fast if agentic search
        # is disabled (imports are deferred).
        self._executor = self._build_executor(openai_api_key, model, max_iterations)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, query: str) -> list[dict[str, Any]]:
        """
        Run the agent for the given query.
        Returns a list of dicts in OpenSearch-hit format so that
        AgenticSearchStrategy._docs_to_results() needs no changes:
          {"_id": ..., "_score": ..., "name": ..., ..., "_event_data": {...}}
        """
        # PII guard — reject queries that contain personal information.
        pii_types = detect_pii(query)
        if pii_types:
            logger.warning(
                "agent_query_contains_pii",
                pii_types=pii_types,
                query_snippet=query[:60],
            )
            return []

        _intermediate_steps: list = []  # captured for fallback even on exception
        t0 = time.perf_counter()

        try:
            result = self._executor.invoke({"input": query})
            _intermediate_steps = result.get("intermediate_steps", [])
            output: str = result.get("output", "")

            # Primary path: output is valid JSON from submit_final_results.
            if output:
                try:
                    raw = json.loads(output)
                    companies = (
                        raw if isinstance(raw, list)
                        else raw.get("companies", []) if isinstance(raw, dict)
                        else []
                    )
                    # Only trust submit_final_results output when it has actual data.
                    # An empty list means the agent called submit_final_results({})
                    # or with an empty array — fall through to step recovery.
                    if companies:
                        return self._normalise_output(companies)
                except json.JSONDecodeError:
                    logger.warning(
                        "agent_output_not_json_recovering_from_steps",
                        output=output[:200],
                    )

            # Fallback: agent didn't produce results via submit_final_results
            # (hit max_iterations, returned plain text, or called submit with {}).
            # Collect every company the tools emitted during the run.
            return self._recover_from_steps(_intermediate_steps)

        except Exception as e:
            logger.error("agent_run_failed", query=query[:100], error=str(e))
            # Even when executor.invoke() throws (e.g. Pydantic validation on a
            # tool call), intermediate steps from earlier tools may still be
            # recoverable if the executor stored them before raising.
            return self._recover_from_steps(_intermediate_steps)
        finally:
            logger.info(
                "agent_run_completed",
                query=query[:100],
                agent_total_ms=int((time.perf_counter() - t0) * 1000),
            )

    # ------------------------------------------------------------------
    # Agent construction
    # ------------------------------------------------------------------

    def _build_executor(self, api_key: str, model: str, max_iterations: int):
        from langchain_openai import ChatOpenAI
        from langchain.agents import create_openai_tools_agent, AgentExecutor
        from langchain.tools import StructuredTool
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

        llm = ChatOpenAI(model=model, temperature=0, api_key=api_key)

        today = date.today()
        prompt = ChatPromptTemplate.from_messages([
            ("system", _SYSTEM_PROMPT_TEMPLATE.format(
                today=today.isoformat(),
                current_year=today.year,
                year_minus_1=today.year - 1,
            )),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        tools = self._build_tools()
        agent = create_openai_tools_agent(llm, tools, prompt)

        return AgentExecutor(
            agent=agent,
            tools=tools,
            max_iterations=max_iterations,
            handle_parsing_errors=True,
            return_intermediate_steps=True,  # required for fallback recovery in run()
            verbose=get_settings().is_development,
        )

    def _build_tools(self):
        from langchain.tools import StructuredTool

        # Capture self once — all tool closures reference this.
        svc = self

        # ── Tool 1: web_search_company_events ─────────────────────────

        def web_search_company_events(query: str) -> str:
            """
            Search the web for recent company events (funding, acquisitions,
            IPOs, layoffs, product launches) and match against the database.
            """
            tavily_hits: list[TavilyResult] = []

            if svc._tavily_key:
                _t_tav = time.perf_counter()
                try:
                    import requests
                    resp = requests.post(
                        "https://api.tavily.com/search",
                        json={
                            "api_key": svc._tavily_key,
                            "query": query,
                            "max_results": svc._tavily_max_results,
                            "search_depth": svc._tavily_search_depth,
                            "include_published_date": True,
                        },
                        timeout=svc._tavily_timeout_s,
                    )
                    resp.raise_for_status()
                    tavily_hits = [
                        TavilyResult.model_validate(r)
                        for r in resp.json().get("results", [])
                    ]
                    logger.info(
                        "tavily_search_done",
                        count=len(tavily_hits),
                        query=query[:80],
                        titles=[h.title[:80] for h in tavily_hits],
                        tavily_ms=int((time.perf_counter() - _t_tav) * 1000),
                    )
                except Exception as e:
                    logger.warning("tavily_search_failed", error=str(e))

            if not tavily_hits:
                return json.dumps({
                    "found": 0,
                    "message": "No web search results available.",
                    "companies": [],
                })

            # Extract structured events with the LLM.
            events: list[CompanyEvent] = []
            results_text = "\n\n".join(
                f"Title: {r.title}\nURL: {r.url}\n"
                f"Published: {r.published_date or 'unknown'}\nContent: {r.content[:1200]}"
                for r in tavily_hits
            )
            user_msg = (
                f"Today: {date.today().isoformat()}\n"
                f"User query: {query}\n\n"
                f"Web search results:\n{results_text}"
            )
            _t_llm = time.perf_counter()
            raw = ""
            try:
                llm_resp = svc._openai.chat.completions.create(
                    model=svc._extraction_model,
                    messages=[
                        {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    max_tokens=svc._llm_max_tokens,
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                raw = llm_resp.choices[0].message.content.strip()
                extraction = EventExtractionResponse.model_validate_json(raw)
                events = extraction.events
                _usage = llm_resp.usage
                logger.info(
                    "events_extracted",
                    count=len(events),
                    query=query[:80],
                    extraction_ms=int((time.perf_counter() - _t_llm) * 1000),
                    input_tokens=_usage.prompt_tokens if _usage else None,
                    output_tokens=_usage.completion_tokens if _usage else None,
                )
            except Exception as e:
                logger.error("event_extraction_failed", error=str(e))
                # Attempt to recover partial events from truncated JSON
                if raw:
                    events = _recover_partial_events(raw)
                    if events:
                        logger.info("partial_events_recovered", count=len(events))

            if not events:
                return json.dumps({
                    "found": 0,
                    "message": "No structured events could be extracted.",
                    "companies": [],
                })

            # Resolve each event's company against OpenSearch.
            resolved: list[dict] = []
            seen_ids: set[str] = set()

            for event in events:
                _event_data = EventData(
                    event_type=event.event_type,
                    amount=event.amount,
                    round=event.round,
                    date=event.date,
                    summary=event.summary,
                    source_url=event.source_url,
                )

                matched = False
                if svc._resolve_to_index:
                    try:
                        resp = svc._opensearch.search(
                            index=svc._index,
                            query={
                                "multi_match": {
                                    "query": event.company_name,
                                    "fields": ["name^3", "domain"],
                                    "type": "best_fields",
                                    "fuzziness": "AUTO",
                                }
                            },
                            size=svc._resolve_per_name,
                        )
                        for hit in resp.get("hits", {}).get("hits", []):
                            doc_id = hit.get("_id")
                            score = float(hit.get("_score", 0))
                            if doc_id not in seen_ids and score > svc._min_resolve_score:
                                seen_ids.add(doc_id)
                                src = hit["_source"]
                                doc = EnrichedCompanyDoc(
                                    id=doc_id,
                                    name=src.get("name", event.company_name),
                                    domain=src.get("domain", ""),
                                    industry=src.get("industry", ""),
                                    country=src.get("country", ""),
                                    locality=src.get("locality", ""),
                                    score=score,
                                    event_data=_event_data,
                                )
                                resolved.append(doc.model_dump())
                                matched = True
                                break
                    except Exception as e:
                        logger.warning(
                            "company_resolution_failed",
                            name=event.company_name,
                            error=str(e),
                        )

                if not matched:
                    # Not in index or resolution disabled — synthetic doc with event data only.
                    synthetic_id = f"synthetic_{hashlib.sha256(event.company_name.encode()).hexdigest()[:16]}"
                    if synthetic_id not in seen_ids:
                        seen_ids.add(synthetic_id)
                        doc = EnrichedCompanyDoc(
                            id=synthetic_id,
                            name=event.company_name,
                            country=event.country or "",
                            locality=event.city or "",
                            score=1.0,
                            event_data=_event_data,
                        )
                        resolved.append(doc.model_dump())

            return json.dumps({"found": len(resolved), "companies": resolved})

        # ── Tool 2: lookup_companies_by_name ──────────────────────────

        def lookup_companies_by_name(company_names: str) -> str:
            """
            Look up specific companies by name in the internal database.
            Input must be a comma-separated list of company names.
            """
            names = [n.strip() for n in company_names.split(",") if n.strip()]
            results: list[dict] = []
            seen_ids: set[str] = set()

            for name in names:
                matched = False
                if svc._resolve_to_index:
                    try:
                        resp = svc._opensearch.search(
                            index=svc._index,
                            query={
                                "multi_match": {
                                    "query": name,
                                    "fields": ["name^3", "domain"],
                                    "type": "best_fields",
                                    "fuzziness": "AUTO",
                                }
                            },
                            size=svc._resolve_per_name,
                        )
                        for hit in resp.get("hits", {}).get("hits", []):
                            doc_id = hit.get("_id")
                            score = float(hit.get("_score", 0))
                            if doc_id not in seen_ids and score > svc._min_resolve_score:
                                seen_ids.add(doc_id)
                                src = hit["_source"]
                                doc = EnrichedCompanyDoc(
                                    id=doc_id,
                                    name=src.get("name", name),
                                    domain=src.get("domain", ""),
                                    industry=src.get("industry", ""),
                                    country=src.get("country", ""),
                                    locality=src.get("locality", ""),
                                    score=score,
                                )
                                results.append(doc.model_dump())
                                matched = True
                    except Exception as e:
                        logger.warning("name_lookup_failed", name=name, error=str(e))

                if not matched:
                    synthetic_id = f"synthetic_{hashlib.sha256(name.encode()).hexdigest()[:16]}"
                    if synthetic_id not in seen_ids:
                        seen_ids.add(synthetic_id)
                        doc = EnrichedCompanyDoc(
                            id=synthetic_id,
                            name=name,
                            score=1.0,
                        )
                        results.append(doc.model_dump())

            return json.dumps({"found": len(results), "companies": results})

        # ── Tool 3: linkedin_profile_lookup ────────────────────────────

        def linkedin_profile_lookup(company_name: str) -> str:
            """
            Look up a company's LinkedIn profile to get detailed company
            information: description, headquarters, industry, size,
            specialties, and recent updates.
            """
            # Step 1: Find company in OpenSearch to get linkedin_url
            linkedin_url: Optional[str] = None
            company_doc: Optional[dict] = None
            try:
                resp = svc._opensearch.search(
                    index=svc._index,
                    query={
                        "multi_match": {
                            "query": company_name,
                            "fields": ["name^3", "domain"],
                            "type": "best_fields",
                            "fuzziness": "AUTO",
                        }
                    },
                    size=1,
                )
                hits = resp.get("hits", {}).get("hits", [])
                if hits:
                    src = hits[0]["_source"]
                    linkedin_url = src.get("linkedin_url")
                    company_doc = {
                        "id": hits[0].get("_id", ""),
                        "name": src.get("name", company_name),
                        "domain": src.get("domain", ""),
                        "industry": src.get("industry", ""),
                        "country": src.get("country", ""),
                        "locality": src.get("locality", ""),
                        "score": float(hits[0].get("_score", 1.0)),
                    }
            except Exception as e:
                logger.warning("linkedin_opensearch_lookup_failed", name=company_name, error=str(e))

            # Step 2: Resolve LinkedIn URL (from index or fallback slug)
            if not linkedin_url:
                import re as _re
                slug = _re.sub(r"[^a-z0-9-]", "", company_name.lower().replace(" ", "-"))
                linkedin_url = f"https://www.linkedin.com/company/{slug}"
                logger.info(
                    "linkedin_url_fallback",
                    company=company_name,
                    fallback_url=linkedin_url,
                )

            # Step 3: Fetch LinkedIn page content via Tavily extract
            profile_data: Optional[dict] = None
            if svc._tavily_key:
                import requests

                url = linkedin_url if linkedin_url.startswith("http") else f"https://{linkedin_url}"
                page_content = ""

                # --- Attempt A: Tavily Extract (direct page scrape) ---
                logger.info("linkedin_attempting_scrape", company=company_name, url=url)
                try:
                    extract_resp = requests.post(
                        "https://api.tavily.com/extract",
                        json={
                            "api_key": svc._tavily_key,
                            "urls": [url],
                        },
                        timeout=svc._tavily_timeout_s,
                    )
                    extract_resp.raise_for_status()
                    extract_results = extract_resp.json().get("results", [])
                    page_content = (
                        extract_results[0].get("raw_content", "") if extract_results else ""
                    )
                    if not page_content:
                        logger.warning(
                            "linkedin_tavily_extract_empty",
                            company=company_name,
                            url=url,
                        )
                except Exception as e:
                    logger.warning(
                        "linkedin_tavily_extract_failed",
                        company=company_name,
                        url=url,
                        error=str(e),
                    )

                # --- Attempt B: Tavily Search fallback (snippet from web) ---
                if not page_content:
                    try:
                        search_resp = requests.post(
                            "https://api.tavily.com/search",
                            json={
                                "api_key": svc._tavily_key,
                                "query": f"{company_name} LinkedIn company profile site:linkedin.com",
                                "max_results": 3,
                                "include_raw_content": True,
                            },
                            timeout=svc._tavily_timeout_s,
                        )
                        search_resp.raise_for_status()
                        search_results = search_resp.json().get("results", [])
                        for sr in search_results:
                            raw_content = sr.get("raw_content") or sr.get("content", "")
                            if raw_content and len(raw_content) > 100:
                                page_content = raw_content
                                logger.info(
                                    "linkedin_tavily_search_fallback_hit",
                                    company=company_name,
                                    source_url=sr.get("url", ""),
                                )
                                break
                        if not page_content:
                            logger.warning(
                                "linkedin_tavily_search_fallback_empty",
                                company=company_name,
                            )
                    except Exception as e:
                        logger.warning(
                            "linkedin_tavily_search_fallback_failed",
                            company=company_name,
                            error=str(e),
                        )

                # --- Step 4: Extract structured profile with LLM ---
                if page_content:
                    try:
                        user_msg = (
                            f"Company: {company_name}\n"
                            f"LinkedIn URL: {url}\n\n"
                            f"Page content:\n{page_content[:3000]}"
                        )
                        llm_resp = svc._openai.chat.completions.create(
                            model=svc._extraction_model,
                            messages=[
                                {"role": "system", "content": _LINKEDIN_EXTRACTION_PROMPT},
                                {"role": "user", "content": user_msg},
                            ],
                            max_tokens=600,
                            temperature=0,
                            response_format={"type": "json_object"},
                        )
                        raw = llm_resp.choices[0].message.content.strip()
                        profile_data = LinkedInProfile.model_validate_json(raw).model_dump()
                        logger.info(
                            "linkedin_profile_extracted",
                            company=company_name,
                            url=url,
                        )
                    except Exception as e:
                        logger.warning(
                            "linkedin_llm_extraction_failed",
                            company=company_name,
                            error=str(e),
                        )
                else:
                    logger.warning(
                        "linkedin_no_page_content",
                        company=company_name,
                        url=url,
                    )

            # Build result
            if company_doc:
                result = dict(company_doc)
            else:
                synthetic_id = f"synthetic_{hashlib.sha256(company_name.encode()).hexdigest()[:16]}"
                result = {
                    "id": synthetic_id,
                    "name": company_name,
                    "domain": "",
                    "industry": "",
                    "country": "",
                    "locality": "",
                    "score": 1.0,
                }
            if profile_data:
                result["linkedin_profile"] = profile_data

            return json.dumps({"found": 1, "companies": [result]})

        # ── Tool 4: submit_final_results ──────────────────────────────

        def submit_final_results(results_json: str = "[]") -> str:
            """
            Submit the final list of companies as the search answer.
            Must be a JSON array of company objects. Call this LAST.
            """
            # Handle non-string input defensively (LangChain edge cases).
            if not isinstance(results_json, str):
                if isinstance(results_json, list):
                    return json.dumps(results_json)
                if isinstance(results_json, dict):
                    return json.dumps(results_json.get("companies", []))
                return "[]"

            # Sanitize literal control characters (e.g. raw \n inside LLM-generated
            # summary strings) that break JSON parsers. Replacing them with a space
            # preserves both string content and JSON structure.
            sanitized = results_json.replace("\r", " ").replace("\t", " ").replace("\n", " ")

            try:
                parsed = json.loads(sanitized)
                if isinstance(parsed, list):
                    return sanitized
                if isinstance(parsed, dict) and "companies" in parsed:
                    return json.dumps(parsed["companies"])
                return "[]"
            except Exception as e:
                logger.warning(
                    "submit_final_results_invalid_json",
                    error=str(e),
                    snippet=sanitized[:200],
                )
                # Return the sanitized raw string — run() will fall back to
                # _recover_from_steps which has the web_search results.
                return sanitized

        return [
            StructuredTool.from_function(
                func=web_search_company_events,
                name="web_search_company_events",
                description=(
                    "Search the web for recent company events (funding, acquisitions, IPOs, "
                    "product launches, layoffs, expansions) and match results against the "
                    "internal company database. Use for any query about company news or events."
                ),
                args_schema=WebSearchInput,
            ),
            StructuredTool.from_function(
                func=lookup_companies_by_name,
                name="lookup_companies_by_name",
                description=(
                    "Look up specific companies by name in the internal database to retrieve "
                    "full profiles: industry, country, employee count, size range, etc. "
                    "Input: comma-separated company names."
                ),
                args_schema=LookupNamesInput,
            ),
            StructuredTool.from_function(
                func=linkedin_profile_lookup,
                name="linkedin_profile_lookup",
                description=(
                    "Look up a company's LinkedIn profile to get detailed information: "
                    "description, headquarters, industry, company size, specialties, "
                    "and recent updates. Use for queries asking about a specific company's "
                    "profile or details."
                ),
                args_schema=LinkedInLookupInput,
            ),
            StructuredTool.from_function(
                func=submit_final_results,
                name="submit_final_results",
                description=(
                    "Submit your final answer as a JSON array of company objects. "
                    "This MUST be your last action — it completes the search task."
                ),
                args_schema=SubmitResultsInput,
                return_direct=True,
            ),
        ]

    # ------------------------------------------------------------------
    # Output normalisation
    # ------------------------------------------------------------------

    def _recover_from_steps(self, steps: list) -> list[dict[str, Any]]:
        """
        Last-resort fallback: scan all intermediate tool call observations for
        companies emitted by web_search_company_events or lookup_companies_by_name.
        Called when the agent did not reach submit_final_results.
        """
        all_companies: list[dict] = []
        seen_ids: set[str] = set()

        for _action, observation in steps:
            if not isinstance(observation, str):
                continue
            try:
                parsed = json.loads(observation)
                companies = (
                    parsed.get("companies", [])
                    if isinstance(parsed, dict)
                    else (parsed if isinstance(parsed, list) else [])
                )
                for c in companies:
                    cid = c.get("id") or c.get("_id", "")
                    if cid and cid not in seen_ids:
                        seen_ids.add(cid)
                        all_companies.append(c)
            except (json.JSONDecodeError, AttributeError):
                continue

        if all_companies:
            logger.info("agent_recovered_from_steps", count=len(all_companies))
        else:
            logger.warning("agent_produced_no_results")
        return self._normalise_output(all_companies)

    def _normalise_output(self, raw_list: list) -> list[dict[str, Any]]:
        """
        Convert EnrichedCompanyDoc dicts to the OpenSearch-hit format that
        AgenticSearchStrategy._docs_to_results() already understands:
          {"_id": ..., "_score": ..., "name": ..., ..., "_event_data": {...}}
        """
        normalised = []
        for item in raw_list:
            try:
                doc = EnrichedCompanyDoc.model_validate(item)
                entry: dict[str, Any] = {
                    "_id": doc.id,
                    "_score": doc.score,
                    "name": doc.name,
                    "domain": doc.domain,
                    "industry": doc.industry,
                    "country": doc.country,
                    "locality": doc.locality,
                }
                if doc.event_data:
                    entry["_event_data"] = doc.event_data.model_dump()
                if doc.linkedin_profile:
                    entry["_linkedin_profile"] = doc.linkedin_profile
                normalised.append(entry)
            except Exception as e:
                logger.warning("output_normalisation_failed", error=str(e))
                normalised.append(item)
        return normalised
