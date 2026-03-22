import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
});

// ── Result shape returned by /api/search/intelligent ──────────────────────
export interface IntelligentCompanyResult {
  id: string;
  name: string;
  domain: string;
  industry: string;
  country: string;
  locality: string;
  relevance_score: number;
  search_method: string;
  ranking_source: string;
  matching_reason?: string;
  year_founded?: number;
  size_range?: string;
  current_employee_estimate?: number;
  event_data?: Record<string, unknown>;
  linkedin_profile?: {
    description?: string;
    headquarters?: string;
    industry?: string;
    company_size?: string;
    specialties?: string[];
    founded_year?: number;
    website?: string;
    recent_updates?: string;
  };
}

export interface IntelligentSearchResponse {
  query: string;
  results: IntelligentCompanyResult[];
  metadata: {
    trace_id: string;
    query_classification: {
      category: string;
      confidence: number;
      reasoning: string;
      needs_external_data: boolean;
      classified_by?: 'regex' | 'llm';
    };
    search_execution: Record<string, unknown>;
    total_results: number;
    response_time_ms: number;
    page: number;
    limit: number;
  };
  status: string;
}

// ── User-selected filters sent alongside the query ─────────────────────────
export interface UserFilters {
  country?: string;
  state?: string;
  city?: string;
  industries?: string[];
  year_from?: number;
  year_to?: number;
  size_range?: string;
}

// ── API calls ──────────────────────────────────────────────────────────────
export const intelligentSearch = async (
  query: string,
  filters?: UserFilters,
  page = 1,
  signal?: AbortSignal,
  limit = 20,
): Promise<IntelligentSearchResponse> => {
  const body: Record<string, unknown> = { query, limit, page, include_reasoning: true };
  if (filters && Object.values(filters).some(v => v !== undefined && v !== '')) {
    body.filters = filters;
  }
  const response = await api.post('/api/search/intelligent', body, { signal });
  return response.data;
};

export const healthCheck = async () => {
  const response = await api.get('/api/search/health');
  return response.data;
};

// ── Client-side autocomplete suggestions ──────────────────────────────────
const SUGGESTION_LIST = [
  'tech companies in California',
  'healthcare companies in London',
  'software companies in San Francisco',
  'AI companies in Seattle',
  'biotech companies in Boston',
  'cybersecurity companies',
  'companies that raised Series B funding',
  'companies with recent IPO',
  'renewable energy companies',
  'manufacturing companies in Germany',
  'media companies in Los Angeles',
  'consulting firms in Chicago',
  'retail companies in UK',
  'companies in Australia',
  'telecommunications companies',
  'find me companies that announced fund raising in last year in Australia',
  'give me more information about Infosys',
];

export function getAutocompleteSuggestions(query: string): string[] {
  const q = query.toLowerCase().trim();
  if (!q || q.length < 2) return [];
  return SUGGESTION_LIST.filter(s => s.toLowerCase().includes(q)).slice(0, 6);
}
