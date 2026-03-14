export interface FiltersState {
  industries: string[];
  sizeRanges: string[];
  country: string;
  state: string;
  city: string;
  year_from?: number;
  year_to?: number;
}

interface FilterPanelProps {
  filters: FiltersState;
  onFiltersChange: (filters: FiltersState) => void;
  onApply: () => void;
  onClear: () => void;
  loading: boolean;
}

const INDUSTRIES = [
  'Information Technology and Services',
  'Computer Software',
  'Internet',
  'Financial Services',
  'Healthcare',
  'Biotechnology',
  'Retail',
  'Manufacturing',
  'Telecommunications',
  'Education Management',
  'Real Estate',
  'Management Consulting',
  'Renewables & Environment',
  'Venture Capital & Private Equity',
];

const COUNTRIES = [
  'United States', 'India', 'United Kingdom', 'Canada', 'Australia',
  'Germany', 'France', 'Japan', 'Brazil', 'Singapore', 'Ireland',
];

const SIZE_OPTIONS = [
  { label: 'Micro (1–10)', value: '1-10' },
  { label: 'Small (11–50)', value: '11-50' },
  { label: 'Small (51–200)', value: '51-200' },
  { label: 'Medium (201–500)', value: '201-500' },
  { label: 'Medium (501–1000)', value: '501-1000' },
  { label: 'Large (1001–5000)', value: '1001-5000' },
  { label: 'Large (5001–10000)', value: '5001-10000' },
  { label: 'Enterprise (10001+)', value: '10001+' },
];

export default function FilterPanel({
  filters,
  onFiltersChange,
  onApply,
  onClear,
  loading,
}: FilterPanelProps) {
  const toggle = (arr: string[], val: string) =>
    arr.includes(val) ? arr.filter(v => v !== val) : [...arr, val];

  return (
    <div className="filter-panel">

      {/* Industry */}
      <div className="filter-group">
        <h3>Industry</h3>
        <div className="filter-scroll-list">
          {INDUSTRIES.map(ind => (
            <label key={ind} className="filter-checkbox">
              <input
                type="checkbox"
                checked={filters.industries.includes(ind)}
                onChange={() =>
                  onFiltersChange({ ...filters, industries: toggle(filters.industries, ind) })
                }
              />
              <span>{ind}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Company Size */}
      <div className="filter-group">
        <h3>Company Size</h3>
        <div className="filter-options">
          {SIZE_OPTIONS.map(({ label, value }) => (
            <label key={value} className="filter-checkbox">
              <input
                type="checkbox"
                checked={filters.sizeRanges.includes(value)}
                onChange={() =>
                  onFiltersChange({ ...filters, sizeRanges: toggle(filters.sizeRanges, value) })
                }
              />
              <span>{label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Location */}
      <div className="filter-group">
        <h3>Location</h3>
        <select
          value={filters.country}
          onChange={e => onFiltersChange({ ...filters, country: e.target.value })}
          className="filter-select"
        >
          <option value="">All Countries</option>
          {COUNTRIES.map(c => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="State / Province (e.g. California)"
          value={filters.state}
          onChange={e => onFiltersChange({ ...filters, state: e.target.value })}
          className="filter-input filter-input-mt"
        />
        <input
          type="text"
          placeholder="City (e.g. San Francisco)"
          value={filters.city}
          onChange={e => onFiltersChange({ ...filters, city: e.target.value })}
          className="filter-input filter-input-mt"
        />
      </div>

      {/* Founding Year */}
      <div className="filter-group">
        <h3>Founding Year</h3>
        <div className="year-inputs">
          <input
            type="number"
            placeholder="From"
            min="1800"
            max="2100"
            value={filters.year_from ?? ''}
            onChange={e =>
              onFiltersChange({
                ...filters,
                year_from: e.target.value ? +e.target.value : undefined,
              })
            }
            className="filter-input-small"
          />
          <span>—</span>
          <input
            type="number"
            placeholder="To"
            min="1800"
            max="2100"
            value={filters.year_to ?? ''}
            onChange={e =>
              onFiltersChange({
                ...filters,
                year_to: e.target.value ? +e.target.value : undefined,
              })
            }
            className="filter-input-small"
          />
        </div>
      </div>

      {/* Tags (placeholder) */}
      <div className="filter-group filter-group-last">
        <h3>Tags</h3>
        <label className="filter-checkbox filter-disabled">
          <input type="checkbox" disabled />
          <span>My Tags</span>
        </label>
        <label className="filter-checkbox filter-disabled" style={{ marginTop: 4 }}>
          <input type="checkbox" disabled />
          <span>Shared Lists</span>
        </label>
        <p className="filter-hint">Tagging coming soon</p>
      </div>

      {/* Buttons */}
      <div className="filter-buttons">
        <button onClick={onClear} className="btn btn-secondary">Clear All</button>
        <button onClick={onApply} disabled={loading} className="btn btn-primary">
          {loading ? 'Searching…' : 'Apply Filters'}
        </button>
      </div>
    </div>
  );
}


const industries = [
  'Information Technology and Services',
  'Software Development',
  'Financial Services',
  'Healthcare',
  'Retail',
  'Manufacturing',
  'Telecommunications',
  'Education',
  'Real Estate',
];

const countries = [
  'United States',
  'Canada',
  'United Kingdom',
  'India',
  'Australia',
  'Germany',
  'France',
  'Japan',
];

const sizes = ['small', 'medium', 'large'];

export default function FilterPanel({ filters, onFiltersChange, onSearch, loading }: FilterPanelProps) {
  const handleIndustryChange = (industry: string) => {
    const newIndustries = filters.industry.includes(industry)
      ? filters.industry.filter(i => i !== industry)
      : [...filters.industry, industry];
    onFiltersChange({ ...filters, industry: newIndustries });
  };

  const handleCountryChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onFiltersChange({ ...filters, country: e.target.value });
  };

  const handleSizeChange = (size: string) => {
    const newSizes = filters.size.includes(size)
      ? filters.size.filter(s => s !== size)
      : [...filters.size, size];
    onFiltersChange({ ...filters, size: newSizes });
  };

  const handleClear = () => {
    onFiltersChange({
      q: '',
      industry: [],
      country: '',
      locality: '',
      year_from: undefined,
      year_to: undefined,
      size: [],
    });
  };

  return (
    <div className="filter-panel">
      <h2>Filters</h2>

      {/* Industry Filter */}
      <div className="filter-group">
        <h3>Industry</h3>
        <div className="filter-options">
          {industries.map(ind => (
            <label key={ind} className="filter-checkbox">
              <input
                type="checkbox"
                checked={filters.industry.includes(ind)}
                onChange={() => handleIndustryChange(ind)}
              />
              <span>{ind}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Country Filter */}
      <div className="filter-group">
        <h3>Country</h3>
        <select value={filters.country} onChange={handleCountryChange} className="filter-select">
          <option value="">All Countries</option>
          {countries.map(country => (
            <option key={country} value={country}>
              {country}
            </option>
          ))}
        </select>
      </div>

      {/* Company Size Filter */}
      <div className="filter-group">
        <h3>Company Size</h3>
        <div className="filter-options">
          {sizes.map(size => (
            <label key={size} className="filter-checkbox">
              <input
                type="checkbox"
                checked={filters.size.includes(size)}
                onChange={() => handleSizeChange(size)}
              />
              <span className="capitalize">{size}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Year Range Filter */}
      <div className="filter-group">
        <h3>Founded Year Range</h3>
        <div className="year-inputs">
          <input
            type="number"
            min="1800"
            max="2100"
            placeholder="From"
            value={filters.year_from || ''}
            onChange={(e) => onFiltersChange({
              ...filters,
              year_from: e.target.value ? parseInt(e.target.value) : undefined
            })}
            className="filter-input-small"
          />
          <span>—</span>
          <input
            type="number"
            min="1800"
            max="2100"
            placeholder="To"
            value={filters.year_to || ''}
            onChange={(e) => onFiltersChange({
              ...filters,
              year_to: e.target.value ? parseInt(e.target.value) : undefined
            })}
            className="filter-input-small"
          />
        </div>
      </div>

      {/* Buttons */}
      <div className="filter-buttons">
        <button onClick={onSearch} disabled={loading} className="btn btn-primary">
          {loading ? 'Searching...' : 'Apply Filters'}
        </button>
        <button onClick={handleClear} className="btn btn-secondary">
          Clear All
        </button>
      </div>
    </div>
  );
}
