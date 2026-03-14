import { useState } from 'react';
import { IntelligentSearchResponse, IntelligentCompanyResult } from '../services/api';

type SortKey = 'relevance' | 'name' | 'year';

interface ResultsListProps {
  results: IntelligentSearchResponse;
  currentPage: number;
  onPageChange: (page: number) => void;
}

const INTENT_META: Record<string, { label: string; color: string }> = {
  regular:  { label: 'Exact Match', color: '#2563eb' },
  semantic: { label: 'Semantic',    color: '#7c3aed' },
  agentic:  { label: 'Agentic',     color: '#d97706' },
};

export default function ResultsList({ results, currentPage, onPageChange }: ResultsListProps) {
  const [sortBy, setSortBy] = useState<SortKey>('relevance');

  const { metadata } = results;
  const totalPages = Math.ceil((metadata?.total_results ?? results.results.length) / (metadata?.limit ?? 20));
  const intent = metadata?.query_classification?.category ?? 'semantic';
  const confidence = metadata?.query_classification?.confidence ?? 0;
  const intentMeta = INTENT_META[intent] ?? INTENT_META.semantic;

  const sorted = [...results.results].sort((a, b) => {
    if (sortBy === 'name') return a.name.localeCompare(b.name);
    if (sortBy === 'year') return (b.year_founded ?? 0) - (a.year_founded ?? 0);
    return b.relevance_score - a.relevance_score;
  });

  if (results.results.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-icon">📂</div>
        <p>No companies found. Try broadening your query or clearing some filters.</p>
      </div>
    );
  }

  return (
    <div className="results-list">
      {/* Header */}
      <div className="results-header">
        <div className="results-header-left">
          <h2>
            Search Results
            <span className="result-count-badge">
              {(metadata?.total_results ?? results.results.length).toLocaleString()} found
            </span>
          </h2>
          <div className="meta-row">
            <span className="intent-badge" style={{ background: intentMeta.color }}>
              {intentMeta.label}
            </span>
            <span className="confidence-text">{Math.round(confidence * 100)}% confidence</span>
            {metadata?.response_time_ms != null && (
              <span className="search-time">{metadata.response_time_ms}ms</span>
            )}
          </div>
          {metadata?.query_classification?.reasoning && (
            <p className="reasoning-text">{metadata.query_classification.reasoning}</p>
          )}
        </div>

        <div className="sort-controls">
          <span className="sort-label">Sort:</span>
          {(['relevance', 'name', 'year'] as SortKey[]).map(key => (
            <button
              key={key}
              className={`sort-btn${sortBy === key ? ' active' : ''}`}
              onClick={() => setSortBy(key)}
            >
              {key.charAt(0).toUpperCase() + key.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Cards */}
      <div className="companies">
        {sorted.map(result => (
          <CompanyCard key={result.id} result={result} />
        ))}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="pagination">
          <button
            className="btn-pagination"
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage <= 1}
          >
            ← Previous
          </button>
          <span className="page-info">
            Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong>
          </span>
          <button
            className="btn-pagination"
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage >= totalPages}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}

function CompanyCard({ result }: { result: IntelligentCompanyResult }) {
  return (
    <div className="company-card">
      <div className="company-header">
        <h3 className="company-name">{result.name}</h3>
        <span className="relevance-badge">{Math.round(result.relevance_score * 100)}% match</span>
      </div>

      <div className="company-info">
        {result.domain && (
          <div className="info-item">
            <span className="label">Domain</span>
            <a href={`https://${result.domain}`} target="_blank" rel="noreferrer">
              {result.domain}
            </a>
          </div>
        )}
        {result.industry && (
          <div className="info-item">
            <span className="label">Industry</span>
            <span>{result.industry}</span>
          </div>
        )}
        <div className="info-item">
          <span className="label">Location</span>
          <span>{[result.locality, result.country].filter(Boolean).join(', ')}</span>
        </div>
        <div className="info-row">
          {result.year_founded != null && (
            <div className="info-item">
              <span className="label">Founded</span>
              <span>{result.year_founded}</span>
            </div>
          )}
          {result.size_range && (
            <div className="info-item">
              <span className="label">Size</span>
              <span>{result.size_range}</span>
            </div>
          )}
        </div>
        {result.current_employee_estimate != null && (
          <div className="info-item">
            <span className="label">Employees</span>
            <span>{result.current_employee_estimate.toLocaleString()}</span>
          </div>
        )}
      </div>

      {result.matching_reason && (
        <div className="matching-reason">💡 {result.matching_reason}</div>
      )}

      <div className="method-tag">{result.search_method} / {result.ranking_source}</div>
    </div>
  );
}


interface ResultsListProps {
  results: SearchResponse;
  currentPage: number;
  onPageChange: (page: number) => void;
  loading: boolean;
}

export default function ResultsList({
  results,
  currentPage,
  onPageChange,
  loading,
}: ResultsListProps) {
  if (loading) {
    return <div className="loading">Loading results...</div>;
  }

  if (results.total === 0) {
    return (
      <div className="empty-state">
        <p>No companies found matching your criteria.</p>
      </div>
    );
  }

  const totalPages = Math.ceil(results.total / results.limit);

  return (
    <div className="results-list">
      <div className="results-header">
        <h2>Search Results</h2>
        <span className="result-count">
          Found <strong>{results.total.toLocaleString()}</strong> companies
          {results.search_time_ms && (
            <span className="search-time"> (in {results.search_time_ms}ms)</span>
          )}
        </span>
      </div>

      {/* Facets / Filters */}
      {results.facets && (results.facets.industries.length > 0 || results.facets.countries.length > 0) && (
        <div className="facets">
          {results.facets.industries.length > 0 && (
            <div className="facet-group">
              <h4>Industries</h4>
              <div className="facet-items">
                {results.facets.industries.slice(0, 5).map(facet => (
                  <span key={facet.name} className="facet-item">
                    {facet.name} <span className="count">({facet.count})</span>
                  </span>
                ))}
              </div>
            </div>
          )}
          {results.facets.countries.length > 0 && (
            <div className="facet-group">
              <h4>Countries</h4>
              <div className="facet-items">
                {results.facets.countries.slice(0, 5).map(facet => (
                  <span key={facet.name} className="facet-item">
                    {facet.name} <span className="count">({facet.count})</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Company Results */}
      <div className="companies">
        {results.results.map((result) => (
          <CompanyCard key={result.company.id} result={result} />
        ))}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="pagination">
          <button
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage === 1}
            className="btn-pagination"
          >
            ← Previous
          </button>

          <div className="page-info">
            Page <strong>{currentPage}</strong> of <strong>{totalPages}</strong>
          </div>

          <button
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
            className="btn-pagination"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}

interface CompanyCardProps {
  result: CompanySearchResult;
}

function CompanyCard({ result }: CompanyCardProps) {
  const company = result.company;

  return (
    <div className="company-card">
      <div className="company-header">
        <h3 className="company-name">{company.name}</h3>
        {result.relevance_score && (
          <span className="relevance-badge">
            {Math.round(result.relevance_score * 100)}% match
          </span>
        )}
      </div>

      <div className="company-info">
        {company.domain && (
          <div className="info-item">
            <span className="label">Domain:</span>
            <a href={`https://${company.domain}`} target="_blank" rel="noreferrer">
              {company.domain}
            </a>
          </div>
        )}

        {company.industry && (
          <div className="info-item">
            <span className="label">Industry:</span>
            <span>{company.industry}</span>
          </div>
        )}

        <div className="info-item">
          <span className="label">Location:</span>
          <span>
            {company.locality}
            {company.locality && company.country && ', '}
            {company.country}
          </span>
        </div>

        <div className="info-row">
          {company.year_founded && (
            <div className="info-item">
              <span className="label">Founded:</span>
              <span>{company.year_founded}</span>
            </div>
          )}
          {company.size_range && (
            <div className="info-item">
              <span className="label">Size:</span>
              <span>{company.size_range}</span>
            </div>
          )}
        </div>

        {company.current_employee_estimate && (
          <div className="info-item">
            <span className="label">Employees:</span>
            <span>{company.current_employee_estimate.toLocaleString()}</span>
          </div>
        )}
      </div>

      {result.matching_reason && (
        <div className="matching-reason">
          💡 {result.matching_reason}
        </div>
      )}

      {company.linkedin_url && (
        <a
          href={`https://${company.linkedin_url}`}
          target="_blank"
          rel="noreferrer"
          className="linkedin-link"
        >
          View on LinkedIn
        </a>
      )}
    </div>
  );
}
