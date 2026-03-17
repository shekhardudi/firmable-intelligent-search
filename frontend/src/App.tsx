import { useState, useEffect, useRef } from 'react';
import {
  intelligentSearch,
  getAutocompleteSuggestions,
  IntelligentSearchResponse,
  UserFilters,
} from './services/api';
import FilterPanel, { FiltersState } from './components/FilterPanel';
import ResultsList from './components/ResultsList';
import './App.css';

// ── Ghost chip extraction (Pillar A) ─────────────────────────────────────

export type IntentChip = { type: 'location' | 'industry' | 'activity' | 'size'; label: string };

const LOC_MAP: Array<[RegExp, string]> = [
  [/\b(california|ca)\b/i, 'California'],
  [/\b(new york|ny|nyc)\b/i, 'New York'],
  [/\b(texas|tx)\b/i, 'Texas'],
  [/\b(london)\b/i, 'London'],
  [/\b(australia)\b/i, 'Australia'],
  [/\b(germany|deutschland)\b/i, 'Germany'],
  [/\b(uk|united kingdom)\b/i, 'United Kingdom'],
  [/\b(europe)\b/i, 'Europe'],
  [/\b(asia)\b/i, 'Asia'],
  [/\b(san francisco|sf)\b/i, 'San Francisco'],
  [/\b(seattle)\b/i, 'Seattle'],
  [/\b(boston)\b/i, 'Boston'],
  [/\b(chicago)\b/i, 'Chicago'],
  [/\b(los angeles|la)\b/i, 'Los Angeles'],
  [/\b(usa|united states|america)\b/i, 'United States'],
  [/\b(canada)\b/i, 'Canada'],
  [/\b(india)\b/i, 'India'],
  [/\b(singapore)\b/i, 'Singapore'],
];

const IND_MAP: Array<[RegExp, string]> = [
  [/\b(tech|technology|software|saas)\b/i, 'Technology'],
  [/\b(fintech|financial tech)\b/i, 'Fintech'],
  [/\b(health(care)?|medical|biotech)\b/i, 'Healthcare'],
  [/\b(ai|artificial intelligence|ml|machine learning)\b/i, 'AI / ML'],
  [/\b(retail|e-?commerce)\b/i, 'Retail'],
  [/\b(energy|renewable|clean energy)\b/i, 'Energy'],
  [/\b(logistics|supply chain)\b/i, 'Logistics'],
  [/\b(media|entertainment)\b/i, 'Media'],
  [/\b(consulting|advisory)\b/i, 'Consulting'],
  [/\b(cybersecurity|security)\b/i, 'Cybersecurity'],
  [/\b(manufacturing)\b/i, 'Manufacturing'],
];

const ACT_MAP: Array<[RegExp, string]> = [
  [/\b(raised|funding|series [a-e]|ipo|acquisition)\b/i, 'Recent Funding'],
  [/\b(hiring|recruiting|growing)\b/i, 'Hiring'],
  [/\b(founded after|started after|new companies?)\b/i, 'Recently Founded'],
  [/\b(startup|early.?stage)\b/i, 'Startup'],
];

const SIZE_MAP: Array<[RegExp, string]> = [
  [/\b(small companies?|smb|sme)\b/i, 'Small Business'],
  [/\b(mid.?market|mid-size)\b/i, 'Mid-Market'],
  [/\b(enterprise)\b/i, 'Enterprise'],
];

function extractChips(text: string): IntentChip[] {
  const chips: IntentChip[] = [];
  const seen = new Set<string>();
  const add = (type: IntentChip['type'], label: string) => {
    if (!seen.has(label)) { seen.add(label); chips.push({ type, label }); }
  };
  for (const [re, label] of LOC_MAP) if (re.test(text)) add('location', label);
  for (const [re, label] of IND_MAP) if (re.test(text)) add('industry', label);
  for (const [re, label] of ACT_MAP) if (re.test(text)) add('activity', label);
  for (const [re, label] of SIZE_MAP) if (re.test(text)) add('size', label);
  return chips.slice(0, 5);
}

// ── AI Thinking Panel ─────────────────────────────────────────────────────

type SearchPhase = 'classifying' | 'searching' | 'ranking';

const PHASE_ORDER: SearchPhase[] = ['classifying', 'searching', 'ranking'];

const PHASE_META: Record<SearchPhase, { label: string; detail: string }> = {
  classifying: { label: 'Understanding your query',  detail: 'Classifying intent with AI…'   },
  searching:   { label: 'Searching companies',        detail: 'Scanning 500k+ companies…'     },
  ranking:     { label: 'Ranking results',            detail: 'Scoring by relevance…'         },
};

function StepIcon({ state }: { state: 'done' | 'active' | 'pending' }) {
  if (state === 'done')   return <span className="ai-step-icon ai-step-icon--done">✓</span>;
  if (state === 'active') return <span className="ai-step-icon ai-step-icon--active"><span className="ai-step-spinner" /></span>;
  return <span className="ai-step-icon ai-step-icon--pending">○</span>;
}

function AIThinkingPanel({ phase, isAgentic }: { phase: SearchPhase; isAgentic: boolean }) {
  return (
    <div className={`ai-thinking${isAgentic ? ' ai-thinking--agentic' : ''}`}>
      <div className="ai-thinking-header">
        <div className="ai-orbit-ring">
          <div className="ai-orbit-dot ai-orbit-dot--1" />
          <div className="ai-orbit-dot ai-orbit-dot--2" />
          <div className="ai-orbit-dot ai-orbit-dot--3" />
        </div>
        <div>
          <h3 className="ai-thinking-title">
            {isAgentic ? '🤖 AI Agent Working' : '✨ AI Searching'}
          </h3>
          <p className="ai-thinking-subtitle">
            {isAgentic ? 'Querying external data sources…' : 'Intelligently processing your query…'}
          </p>
        </div>
      </div>
      <div className="ai-steps">
        {PHASE_ORDER.map((p, i) => {
          const currentIdx = PHASE_ORDER.indexOf(phase);
          const state: 'done' | 'active' | 'pending' =
            i < currentIdx ? 'done' : i === currentIdx ? 'active' : 'pending';
          return (
            <div key={p} className={`ai-step ai-step--${state}`}>
              <StepIcon state={state} />
              <span className="ai-step-label">{PHASE_META[p].label}</span>
              {state === 'active' && (
                <span className="ai-step-detail">{PHASE_META[p].detail}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── App ───────────────────────────────────────────────────────────────────

const EMPTY_FILTERS: FiltersState = {
  industries: [],
  sizeRanges: [],
  country: '',
  state: '',
  city: '',
};

const CHIP_ICON: Record<IntentChip['type'], string> = {
  location: '📍',
  industry: '🏭',
  activity: '⚡',
  size: '📊',
};

export default function App() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<IntelligentSearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [filters, setFilters] = useState<FiltersState>(EMPTY_FILTERS);

  // AI thinking animation state
  const [searchPhase, setSearchPhase] = useState<SearchPhase>('classifying');
  const [lastIntent, setLastIntent] = useState('semantic');
  const phaseIntervalRef = useRef<number | null>(null);

  // Autocomplete state
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [activeSuggestion, setActiveSuggestion] = useState(-1);

  // Ghost chips + AI glow (Pillars A + B)
  const [ghostChips, setGhostChips] = useState<IntentChip[]>([]);
  const [aiGlowing, setAiGlowing] = useState(false);
  const [aiDetectedIndustries, setAiDetectedIndustries] = useState<string[]>([]);
  const [aiDetectedCountry, setAiDetectedCountry] = useState('');
  const glowTimerRef = useRef<number | null>(null);

  // Update ghost chips as user types (Pillar A)
  useEffect(() => {
    setGhostChips(extractChips(query));
  }, [query]);

  // Advance through search phases while loading
  useEffect(() => {
    if (loading) {
      setSearchPhase('classifying');
      let idx = 0;
      phaseIntervalRef.current = window.setInterval(() => {
        idx = Math.min(idx + 1, PHASE_ORDER.length - 1);
        setSearchPhase(PHASE_ORDER[idx]);
        if (idx === PHASE_ORDER.length - 1) clearInterval(phaseIntervalRef.current!);
      }, 800);
    } else {
      if (phaseIntervalRef.current !== null) {
        clearInterval(phaseIntervalRef.current);
        phaseIntervalRef.current = null;
      }
    }
    return () => {
      if (phaseIntervalRef.current !== null) clearInterval(phaseIntervalRef.current);
    };
  }, [loading]);

  // Debounced autocomplete suggestions
  useEffect(() => {
    if (!query.trim() || query.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    const timer = setTimeout(() => {
      const hits = getAutocompleteSuggestions(query);
      setSuggestions(hits);
      setShowSuggestions(hits.length > 0);
      setActiveSuggestion(-1);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const toApiFilters = (f: FiltersState): UserFilters => {
    const out: UserFilters = {};
    if (f.industries.length > 0) out.industries = f.industries;
    if (f.sizeRanges.length > 0) out.size_range = f.sizeRanges[0];
    if (f.country) out.country = f.country;
    if (f.state) out.state = f.state;
    if (f.city) out.city = f.city;
    if (f.year_from) out.year_from = f.year_from;
    if (f.year_to) out.year_to = f.year_to;
    return out;
  };

  const runSearch = async (searchQuery: string, page: number, currentFilters: FiltersState) => {
    if (!searchQuery.trim()) return;
    // Strip wrapping quotes if the entire string is quoted
    let cleaned = searchQuery.trim();
    if (cleaned.length >= 2 && cleaned.startsWith('"') && cleaned.endsWith('"')) {
      cleaned = cleaned.slice(1, -1);
      setQuery(cleaned);
    }
    setLoading(true);
    try {
      const apiFilters = toApiFilters(currentFilters);
      const data = await intelligentSearch(cleaned, apiFilters, page);
      setResults(data);
      setLastIntent(data.metadata?.query_classification?.category ?? 'semantic');
      // Pillar B – AI glow on filter panel for detected intent
      const chips = extractChips(searchQuery);
      const indChips = chips.filter(c => c.type === 'industry').map(c => c.label);
      const locChip  = chips.find(c => c.type === 'location');
      if (indChips.length > 0 || locChip) {
        setAiDetectedIndustries(indChips);
        setAiDetectedCountry(locChip?.label ?? '');
        setAiGlowing(true);
        if (glowTimerRef.current !== null) clearTimeout(glowTimerRef.current);
        glowTimerRef.current = window.setTimeout(() => {
          setAiGlowing(false);
          glowTimerRef.current = null;
        }, 2500);
      }
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const selectSuggestion = (s: string) => {
    setQuery(s);
    setShowSuggestions(false);
    setActiveSuggestion(-1);
    setCurrentPage(1);
    runSearch(s, 1, filters);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showSuggestions || suggestions.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveSuggestion(prev => Math.min(prev + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveSuggestion(prev => Math.max(prev - 1, -1));
    } else if (e.key === 'Enter' && activeSuggestion >= 0) {
      e.preventDefault();
      selectSuggestion(suggestions[activeSuggestion]);
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setShowSuggestions(false);
    setCurrentPage(1);
    runSearch(query, 1, filters);
  };

  const handleApplyFilters = () => {
    setCurrentPage(1);
    runSearch(query, 1, filters);
  };

  const handleClearFilters = () => {
    const cleared = EMPTY_FILTERS;
    setFilters(cleared);
    setCurrentPage(1);
    if (query.trim()) runSearch(query, 1, cleared);
  };

  const handleClearAiFilters = () => {
    setAiDetectedIndustries([]);
    setAiDetectedCountry('');
    setAiGlowing(false);
  };

  const handleBrandClick = () => {
    setQuery('');
    setResults(null);
    setFilters(EMPTY_FILTERS);
    setCurrentPage(1);
    setGhostChips([]);
    setAiGlowing(false);
    setAiDetectedIndustries([]);
    setAiDetectedCountry('');
    setSuggestions([]);
    setShowSuggestions(false);
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    runSearch(query, page, filters);
  };

  return (
    <div className="app">
      {/* ── Sticky top nav with omnibox ── */}
      <header className="top-nav">
        <div className="top-nav-inner">
          <button type="button" className="top-nav-brand" onClick={handleBrandClick}>
            Firmable
          </button>

          <div className="omnibox-wrap">
            <form className="omnibox" onSubmit={handleSubmit}>
              <span className="omnibox-icon">🔍</span>
              <input
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
                placeholder='Search companies… e.g. "tech startups in California"'
                className="omnibox-input"
                disabled={loading}
                autoComplete="off"
              />
              <button
                type="submit"
                className="omnibox-btn"
                disabled={loading || !query.trim()}
              >
                {loading ? '…' : 'Search'}
              </button>
            </form>

            {/* Ghost chips — live intent preview (Pillar A) */}
            {ghostChips.length > 0 && (
              <div className="ghost-chips">
                {ghostChips.map(chip => (
                  <span key={chip.label} className={`ghost-chip ghost-chip--${chip.type}`}>
                    {CHIP_ICON[chip.type]} {chip.label}
                  </span>
                ))}
              </div>
            )}

            {/* Autocomplete dropdown */}
            {showSuggestions && suggestions.length > 0 && (
              <div className="autocomplete-dropdown">
                {suggestions.map((s, i) => (
                  <div
                    key={s}
                    className={`autocomplete-item${i === activeSuggestion ? ' autocomplete-item--active' : ''}`}
                    onMouseDown={() => selectSuggestion(s)}
                  >
                    <span className="autocomplete-icon">🔍</span> {s}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="dashboard">
        {/* Sidebar: filters only */}
        <aside className="sidebar">
          <FilterPanel
            filters={filters}
            onFiltersChange={setFilters}
            onApply={handleApplyFilters}
            onClear={handleClearFilters}
            loading={loading}
            aiHighlights={{
              industries: aiDetectedIndustries,
              country: aiDetectedCountry,
              glowing: aiGlowing,
            }}
            onClearAiFilters={handleClearAiFilters}
          />
        </aside>

        {/* Main results area */}
        <main className="results-panel">
          {loading && (
            <AIThinkingPanel phase={searchPhase} isAgentic={lastIntent === 'agentic'} />
          )}

          {!loading && results && (
            <ResultsList
              results={results}
              currentPage={currentPage}
              onPageChange={handlePageChange}
              searchQuery={query}
            />
          )}

          {!loading && !results && (
            <div className="empty-state">
              <div className="empty-icon">🔍</div>
              <p>Search using natural language — try one of these:</p>
              <ul>
                <li>"Apple Inc", "IBM Inc", "Google"</li>
                <li>"tech companies in California"</li>
                <li>"find me companies that announced fund raising last year in USA"</li>
                <li>"give me more information about Infosys"</li>
              </ul>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

