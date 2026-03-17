import { useState } from 'react';
import { IntelligentSearchResponse, IntelligentCompanyResult } from '../services/api';

type SortKey = 'relevance' | 'name' | 'year';

interface ResultsListProps {
  results: IntelligentSearchResponse;
  currentPage: number;
  onPageChange: (page: number) => void;
  searchQuery: string;
}

// ── Intent config (Pillar C) ──────────────────────────────────────────────

const INTENT_CFG: Record<string, {
  label: string;
  color: string;
  className: string;
  banner: (q: string, n: number) => string;
}> = {
  regular: {
    label: 'Exact Match',
    color: '#2563eb',
    className: 'intent--regular',
    banner: (q, n) => `${n.toLocaleString()} companies matching "${q}"`,
  },
  semantic: {
    label: 'Semantic',
    color: '#7c3aed',
    className: 'intent--semantic',
    banner: (q, n) => `${n.toLocaleString()} semantically related results for "${q}"`,
  },
  agentic: {
    label: '🤖 Agentic',
    color: '#d97706',
    className: 'intent--agentic',
    banner: (_q, n) => `AI agent surfaced ${n.toLocaleString()} companies using live data`,
  },
};

const INTENT_DEFAULT = INTENT_CFG.semantic;

// ── Helpers ───────────────────────────────────────────────────────────────

const AVATAR_COLORS = [
  '#6366f1', '#0ea5e9', '#10b981', '#f59e0b',
  '#ef4444', '#8b5cf6', '#14b8a6', '#f97316',
];

function getAvatarColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function relevanceColor(score: number): string {
  if (score >= 0.8) return '#10b981';
  if (score >= 0.5) return '#f59e0b';
  return '#94a3b8';
}

// ── Component ─────────────────────────────────────────────────────────────

export default function ResultsList({ results, currentPage, onPageChange, searchQuery }: ResultsListProps) {
  const [sortBy, setSortBy] = useState<SortKey>('relevance');

  const { metadata } = results;
  const totalPages = Math.ceil(
    (metadata?.total_results ?? results.results.length) / (metadata?.limit ?? 20),
  );
  const intent = metadata?.query_classification?.category ?? 'semantic';
  const confidence = metadata?.query_classification?.confidence ?? 0;
  const needsExternalData = metadata?.query_classification?.needs_external_data ?? false;
  const cfg = INTENT_CFG[intent] ?? INTENT_DEFAULT;
  const totalCount = metadata?.total_results ?? results.results.length;

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
      {/* Intent banner (Pillar C) */}
      <div className={`intent-banner intent-banner--${intent}`}>
        <span className="intent-banner-dot" style={{ background: cfg.color }} />
        <span className="intent-banner-text">{cfg.banner(searchQuery, totalCount)}</span>
        <div className="intent-banner-meta">
          <span className="intent-badge" style={{ background: cfg.color }}>{cfg.label}</span>
          {needsExternalData && <span className="live-data-chip">🌐 Live data</span>}
          <span className="confidence-text">{Math.round(confidence * 100)}% confidence</span>
          {metadata?.response_time_ms != null && (
            <span className="search-time">{metadata.response_time_ms}ms</span>
          )}
        </div>
      </div>

      {metadata?.query_classification?.reasoning && (
        <p className="reasoning-text">{metadata.query_classification.reasoning}</p>
      )}

      {/* Sort row */}
      <div className="sort-row">
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
  const initials = result.name
    .split(/\s+/)
    .slice(0, 2)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('');
  const avatarColor = getAvatarColor(result.name);
  const relColor    = relevanceColor(result.relevance_score);

  const eventEntries = result.event_data
    ? Object.entries(result.event_data).filter(([, v]) => v != null && v !== '')
    : [];

  const pills = [
    result.industry,
    result.size_range,
    result.year_founded ? `Est. ${result.year_founded}` : null,
  ].filter(Boolean) as string[];

  return (
    <div className="company-card">
      <div className="company-card-top">
        {/* Avatar */}
        <div className="company-avatar" style={{ background: avatarColor }}>
          {initials}
        </div>

        {/* Name + domain + pills */}
        <div className="company-main">
          <div className="company-name-row">
            <h3 className="company-name">{result.name}</h3>
            <span className="relevance-dot" style={{ background: relColor }} title={`${Math.round(result.relevance_score * 100)}% match`} />
          </div>
          {result.domain && (
            <a href={`https://${result.domain}`} className="company-domain" target="_blank" rel="noreferrer">
              {result.domain}
            </a>
          )}
          <div className="meta-pills">
            {pills.map(p => (
              <span key={p} className="meta-pill">{p}</span>
            ))}
            {[result.locality, result.country].filter(Boolean).length > 0 && (
              <span className="meta-pill meta-pill--location">
                📍 {[result.locality, result.country].filter(Boolean).join(', ')}
              </span>
            )}
          </div>
        </div>

        {/* Relevance % */}
        <span className="relevance-badge" style={{ color: relColor, borderColor: relColor + '40' }}>
          {Math.round(result.relevance_score * 100)}%
        </span>
      </div>

      {result.matching_reason && (
        <div className="matching-reason">💡 {result.matching_reason}</div>
      )}

      {result.linkedin_profile?.description && (
        <div className="company-description">
          <p>{result.linkedin_profile.description}</p>
          {result.linkedin_profile.specialties && result.linkedin_profile.specialties.length > 0 && (
            <div className="company-specialties">
              {result.linkedin_profile.specialties.map(s => (
                <span key={s} className="specialty-pill">{s}</span>
              ))}
            </div>
          )}
          {result.linkedin_profile.recent_updates && (
            <div className="company-recent-updates">
              <span className="recent-updates-label">Recent updates:</span> {result.linkedin_profile.recent_updates}
            </div>
          )}
        </div>
      )}

      {result.current_employee_estimate != null && (
        <div className="employee-count">
          👥 {result.current_employee_estimate.toLocaleString()} employees
        </div>
      )}

      {eventEntries.length > 0 && (
        <div className="event-data-block">
          <div className="event-data-title">📰 Recent Activity</div>
          {eventEntries.filter(([k]) => k !== 'source_url').slice(0, 5).map(([k, v]) => (
            <div key={k} className="event-data-item">
              <span className="event-data-key">{k.replace(/_/g, ' ')}</span>
              <span>{String(v)}</span>
            </div>
          ))}
          {result.event_data?.source_url ? (
            <a
              className="news-link"
              href={String(result.event_data.source_url)}
              target="_blank"
              rel="noreferrer"
            >
              📰 Read full article →
            </a>
          ) : null}
        </div>
      )}

      <div className="method-tag">{result.search_method} / {result.ranking_source}</div>
    </div>
  );
}
