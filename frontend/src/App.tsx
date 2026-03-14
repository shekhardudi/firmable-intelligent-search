import { useState } from 'react';
import {
  intelligentSearch,
  IntelligentSearchResponse,
  UserFilters,
} from './services/api';
import FilterPanel, { FiltersState } from './components/FilterPanel';
import ResultsList from './components/ResultsList';
import './App.css';

const EMPTY_FILTERS: FiltersState = {
  industries: [],
  sizeRanges: [],
  country: '',
  state: '',
  city: '',
};

export default function App() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<IntelligentSearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [filters, setFilters] = useState<FiltersState>(EMPTY_FILTERS);

  /** Convert internal FiltersState to the UserFilters shape the API expects. */
  const toApiFilters = (f: FiltersState): UserFilters => {
    const out: UserFilters = {};
    // Send only the first selected value for single-value fields
    if (f.industries.length > 0) out.industry = f.industries[0];
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
    setLoading(true);
    try {
      const apiFilters = toApiFilters(currentFilters);
      const data = await intelligentSearch(searchQuery.trim(), apiFilters, page);
      setResults(data);
    } catch (err) {
      console.error('Search failed:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
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

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    runSearch(query, page, filters);
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>🔍 Company Search</h1>
        <p>AI-powered search — try natural language or use filters</p>
      </header>

      <div className="dashboard">
        {/* Left: search bar + filters */}
        <aside className="sidebar">
          <div className="search-box">
            <form onSubmit={handleSubmit}>
              <input
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder='Search… e.g., "tech companies in California"'
                className="search-input"
                disabled={loading}
              />
              <button
                type="submit"
                className="search-btn"
                disabled={loading || !query.trim()}
              >
                {loading ? '…' : 'Search'}
              </button>
            </form>
          </div>

          <FilterPanel
            filters={filters}
            onFiltersChange={setFilters}
            onApply={handleApplyFilters}
            onClear={handleClearFilters}
            loading={loading}
          />
        </aside>

        {/* Right: results */}
        <main className="results-panel">
          {loading && (
            <div className="loading-state">
              <div className="loading-spinner" />
              <p>Searching…</p>
            </div>
          )}

          {!loading && results && (
            <ResultsList
              results={results}
              currentPage={currentPage}
              onPageChange={handlePageChange}
            />
          )}

          {!loading && !results && (
            <div className="empty-state">
              <div className="empty-icon">🔍</div>
              <p>Search using natural language or select filters on the left</p>
              <ul>
                <li>"tech companies in California"</li>
                <li>"sustainable energy startups in Europe"</li>
                <li>"companies that raised funding recently"</li>
              </ul>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
