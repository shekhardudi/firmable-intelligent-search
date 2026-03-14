import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

// ---- Intelligent search types ----

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
    };
    search_execution: Record<string, unknown>;
    total_results: number;
    response_time_ms: number;
    page: number;
    limit: number;
  };
  status: string;
}

export interface UserFilters {
  country?: string;
  state?: string;
  city?: string;
  industry?: string;
  year_from?: number;
  year_to?: number;
  size_range?: string;
}

export const intelligentSearch = async (
  query: string,
  filters?: UserFilters,
  page = 1,
  limit = 20,
): Promise<IntelligentSearchResponse> => {
  const body: Record<string, unknown> = { query, limit, page, include_reasoning: true };
  if (filters && Object.values(filters).some(v => v !== undefined && v !== '')) {
    body.filters = filters;
  }
  const response = await api.post('/api/search/intelligent', body);
  return response.data;
};

export const healthCheck = async () => {
  const response = await api.get('/api/search/health');
  return response.data;
};


const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
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
  industry?: string;
  year_from?: number;
  year_to?: number;
  size_range?: string;
}

// ── API calls ──────────────────────────────────────────────────────────────
export const intelligentSearch = async (
  query: string,
  filters?: UserFilters,
  page = 1,
  limit = 20,
): Promise<IntelligentSearchResponse> => {
  const body: Record<string, unknown> = { query, limit, page, include_reasoning: true };
  if (filters && Object.values(filters).some(v => v !== undefined && v !== '')) {
    body.filters = filters;
  }
  const response = await api.post('/api/search/intelligent', body);
  return response.data;
};

export const healthCheck = async () => {
  const response = await api.get('/api/search/health');
  return response.data;
};
