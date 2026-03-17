import { useState, useRef, useEffect } from 'react';

export interface FiltersState {
  industries: string[];
  sizeRanges: string[];
  country: string;
  state: string;
  city: string;
  year_from?: number;
  year_to?: number;
}

export interface AiHighlights {
  industries: string[];
  country: string;
  glowing: boolean;
}

interface FilterPanelProps {
  filters: FiltersState;
  onFiltersChange: (filters: FiltersState) => void;
  onApply: () => void;
  onClear: () => void;
  loading: boolean;
  aiHighlights?: AiHighlights;
  onClearAiFilters?: () => void;
}

const INDUSTRIES = [
  'Accounting',
  'Airlines/Aviation',
  'Alternative Dispute Resolution',
  'Alternative Medicine',
  'Animation',
  'Apparel & Fashion',
  'Architecture & Planning',
  'Arts and Crafts',
  'Automotive',
  'Aviation & Aerospace',
  'Banking',
  'Biotechnology',
  'Broadcast Media',
  'Building Materials',
  'Business Supplies and Equipment',
  'Capital Markets',
  'Chemicals',
  'Civic & Social Organization',
  'Civil Engineering',
  'Commercial Real Estate',
  'Computer & Network Security',
  'Computer Games',
  'Computer Hardware',
  'Computer Networking',
  'Computer Software',
  'Construction',
  'Consumer Electronics',
  'Consumer Goods',
  'Consumer Services',
  'Cosmetics',
  'Dairy',
  'Defense & Space',
  'Design',
  'E-Learning',
  'Education Management',
  'Electrical/Electronic Manufacturing',
  'Entertainment',
  'Environmental Services',
  'Events Services',
  'Executive Office',
  'Facilities Services',
  'Farming',
  'Financial Services',
  'Fine Art',
  'Fishery',
  'Food & Beverages',
  'Food Production',
  'Fund-Raising',
  'Furniture',
  'Gambling & Casinos',
  'Glass, Ceramics & Concrete',
  'Government Administration',
  'Government Relations',
  'Graphic Design',
  'Health, Wellness and Fitness',
  'Higher Education',
  'Hospital & Health Care',
  'Hospitality',
  'Human Resources',
  'Import and Export',
  'Individual & Family Services',
  'Industrial Automation',
  'Information Services',
  'Information Technology and Services',
  'Insurance',
  'International Affairs',
  'International Trade and Development',
  'Internet',
  'Investment Banking',
  'Investment Management',
  'Judiciary',
  'Law Enforcement',
  'Law Practice',
  'Legal Services',
  'Legislative Office',
  'Leisure, Travel & Tourism',
  'Libraries',
  'Logistics and Supply Chain',
  'Luxury Goods & Jewelry',
  'Machinery',
  'Management Consulting',
  'Maritime',
  'Market Research',
  'Marketing and Advertising',
  'Mechanical or Industrial Engineering',
  'Media Production',
  'Medical Devices',
  'Medical Practice',
  'Mental Health Care',
  'Military',
  'Mining & Metals',
  'Motion Pictures and Film',
  'Museums and Institutions',
  'Music',
  'Nanotechnology',
  'Newspapers',
  'Non-Profit Organization Management',
  'Oil & Energy',
  'Online Media',
  'Outsourcing/Offshoring',
  'Package/Freight Delivery',
  'Packaging and Containers',
  'Paper & Forest Products',
  'Performing Arts',
  'Pharmaceuticals',
  'Philanthropy',
  'Photography',
  'Plastics',
  'Political Organization',
  'Primary/Secondary Education',
  'Printing',
  'Professional Training & Coaching',
  'Program Development',
  'Public Policy',
  'Public Relations and Communications',
  'Public Safety',
  'Publishing',
  'Railroad Manufacture',
  'Ranching',
  'Real Estate',
  'Recreational Facilities and Services',
  'Religious Institutions',
  'Renewables & Environment',
  'Research',
  'Restaurants',
  'Retail',
  'Security and Investigations',
  'Semiconductors',
  'Shipbuilding',
  'Sporting Goods',
  'Sports',
  'Staffing and Recruiting',
  'Supermarkets',
  'Telecommunications',
  'Textiles',
  'Think Tanks',
  'Tobacco',
  'Translation and Localization',
  'Transportation/Trucking/Railroad',
  'Utilities',
  'Venture Capital & Private Equity',
  'Veterinary',
  'Warehousing',
  'Wholesale',
  'Wine and Spirits',
  'Wireless',
  'Writing and Editing',
];

const COUNTRIES = [
  'Afghanistan', 'Albania', 'Algeria', 'American Samoa', 'Andorra', 'Angola',
  'Anguilla', 'Antigua and Barbuda', 'Argentina', 'Armenia', 'Aruba', 'Australia',
  'Austria', 'Azerbaijan', 'Bahamas', 'Bahrain', 'Bangladesh', 'Barbados',
  'Belarus', 'Belgium', 'Belize', 'Benin', 'Bermuda', 'Bhutan', 'Bolivia',
  'Bosnia and Herzegovina', 'Botswana', 'Brazil', 'British Virgin Islands',
  'Brunei', 'Bulgaria', 'Burkina Faso', 'Burundi', 'Cambodia', 'Cameroon',
  'Canada', 'Cape Verde', 'Caribbean Netherlands', 'Cayman Islands',
  'Central African Republic', 'Chad', 'Chile', 'China', 'Colombia', 'Comoros',
  'Cook Islands', 'Costa Rica', 'Croatia', 'Cuba', 'Cura\u00e7ao', 'Cyprus',
  'Czechia', "C\u00f4te d'Ivoire", 'Democratic Republic of the Congo', 'Denmark',
  'Djibouti', 'Dominica', 'Dominican Republic', 'Ecuador', 'Egypt', 'El Salvador',
  'Equatorial Guinea', 'Eritrea', 'Estonia', 'Ethiopia', 'Faroe Islands', 'Fiji',
  'Finland', 'France', 'French Guiana', 'French Polynesia', 'Gabon', 'Gambia',
  'Georgia', 'Germany', 'Ghana', 'Gibraltar', 'Greece', 'Greenland', 'Grenada',
  'Guadeloupe', 'Guam', 'Guatemala', 'Guernsey', 'Guinea', 'Guinea-Bissau',
  'Guyana', 'Haiti', 'Honduras', 'Hong Kong', 'Hungary', 'Iceland', 'India',
  'Indonesia', 'Iran', 'Iraq', 'Ireland', 'Isle of Man', 'Israel', 'Italy',
  'Jamaica', 'Japan', 'Jersey', 'Jordan', 'Kazakhstan', 'Kenya', 'Kiribati',
  'Kosovo', 'Kuwait', 'Kyrgyzstan', 'Laos', 'Latvia', 'Lebanon', 'Lesotho',
  'Liberia', 'Libya', 'Liechtenstein', 'Lithuania', 'Luxembourg', 'Macau',
  'Macedonia', 'Madagascar', 'Malawi', 'Malaysia', 'Maldives', 'Mali', 'Malta',
  'Marshall Islands', 'Martinique', 'Mauritania', 'Mauritius', 'Mayotte',
  'Mexico', 'Micronesia', 'Moldova', 'Monaco', 'Mongolia', 'Montenegro',
  'Montserrat', 'Morocco', 'Mozambique', 'Myanmar', 'Namibia', 'Nepal',
  'Netherlands', 'Netherlands Antilles', 'New Caledonia', 'New Zealand',
  'Nicaragua', 'Niger', 'Nigeria', 'Niue', 'Norfolk Island', 'North Korea',
  'Northern Mariana Islands', 'Norway', 'Oman', 'Pakistan', 'Palau', 'Palestine',
  'Panama', 'Papua New Guinea', 'Paraguay', 'Peru', 'Philippines', 'Poland',
  'Portugal', 'Puerto Rico', 'Qatar', 'Republic of the Congo', 'Romania',
  'Russia', 'Rwanda', 'R\u00e9union', 'Saint Barth\u00e9lemy', 'Saint Helena',
  'Saint Kitts and Nevis', 'Saint Lucia', 'Saint Martin',
  'Saint Pierre and Miquelon', 'Saint Vincent and the Grenadines', 'Samoa',
  'San Marino', 'Saudi Arabia', 'Senegal', 'Serbia', 'Seychelles',
  'Sierra Leone', 'Singapore', 'Sint Maarten', 'Slovakia', 'Slovenia',
  'Solomon Islands', 'Somalia', 'South Africa', 'South Korea', 'South Sudan',
  'Spain', 'Sri Lanka', 'Sudan', 'Suriname', 'Svalbard and Jan Mayen',
  'Swaziland', 'Sweden', 'Switzerland', 'Syria', 'S\u00e3o Tom\u00e9 and Pr\u00edncipe',
  'Taiwan', 'Tajikistan', 'Tanzania', 'Thailand', 'Timor-Leste', 'Togo',
  'Tonga', 'Trinidad and Tobago', 'Tunisia', 'Turkey', 'Turkmenistan',
  'Turks and Caicos Islands', 'Tuvalu', 'U.S. Virgin Islands', 'Uganda',
  'Ukraine', 'United Arab Emirates', 'United Kingdom', 'United States',
  'Uruguay', 'Uzbekistan', 'Vanuatu', 'Venezuela', 'Vietnam', 'Western Sahara',
  'Yemen', 'Zambia', 'Zimbabwe', '\u00c5land Islands',
];

/* values stay identical for backend compatibility — only labels changed */
const SIZE_OPTIONS = [
  { label: 'Micro (1–10)',          value: '1 - 10' },
  { label: 'Small (11–50)',         value: '11 - 50' },
  { label: 'Growth (51–200)',       value: '51 - 200' },
  { label: 'Mid-Market (201–500)',  value: '201 - 500' },
  { label: 'Scaleup (501–1 000)',   value: '501 - 1000' },
  { label: 'Large (1 001–5 000)',   value: '1001 - 5000' },
  { label: 'Major (5 001–10 000)',  value: '5001 - 10000' },
  { label: 'Enterprise (10 001+)',  value: '10001+' },
];

/* ── helpers ───────────────────────────────────────────────────────────── */

function countActiveFilters(f: FiltersState): number {
  let n = 0;
  n += f.industries.length;
  n += f.sizeRanges.length;
  if (f.country) n++;
  if (f.state) n++;
  if (f.city) n++;
  if (f.year_from !== undefined) n++;
  if (f.year_to !== undefined) n++;
  return n;
}

function sectionActiveCount(section: string, f: FiltersState): number {
  switch (section) {
    case 'industry': return f.industries.length;
    case 'size':     return f.sizeRanges.length;
    case 'location': return (f.country ? 1 : 0) + (f.state ? 1 : 0) + (f.city ? 1 : 0);
    case 'year':     return (f.year_from !== undefined ? 1 : 0) + (f.year_to !== undefined ? 1 : 0);
    default:         return 0;
  }
}

/* ── component ─────────────────────────────────────────────────────────── */

export default function FilterPanel({
  filters,
  onFiltersChange,
  onApply,
  onClear,
  loading,
  aiHighlights,
  onClearAiFilters,
}: FilterPanelProps) {
  const toggle = (arr: string[], val: string) =>
    arr.includes(val) ? arr.filter(v => v !== val) : [...arr, val];

  /* collapsible sections — all open by default */
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const toggleSection = (key: string) =>
    setCollapsed(prev => ({ ...prev, [key]: !prev[key] }));

  /* industry search */
  const [industrySearch, setIndustrySearch] = useState('');

  /* country search dropdown */
  const [countrySearch, setCountrySearch] = useState('');
  const [countryOpen, setCountryOpen] = useState(false);
  const countryRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (countryRef.current && !countryRef.current.contains(e.target as Node))
        setCountryOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  /* AI highlight helpers */
  const isAiHighlightedIndustry = (ind: string) => {
    if (!aiHighlights?.glowing || !aiHighlights.industries.length) return false;
    const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
    return aiHighlights.industries.some(ai => norm(ind).includes(norm(ai)) || norm(ai).includes(norm(ind)));
  };

  const isAiHighlightedCountry = (c: string) => {
    if (!aiHighlights?.glowing || !aiHighlights.country) return false;
    return c.toLowerCase().includes(aiHighlights.country.toLowerCase()) ||
           aiHighlights.country.toLowerCase().includes(c.toLowerCase());
  };

  const hasAiHighlights = aiHighlights?.glowing &&
    (aiHighlights.industries.length > 0 || !!aiHighlights.country);

  /* derived data */
  const totalActive = countActiveFilters(filters);

  const filteredIndustries = industrySearch
    ? INDUSTRIES.filter(i => i.toLowerCase().includes(industrySearch.toLowerCase()))
    : INDUSTRIES;

  /* sort: selected first, then AI-highlighted, then alphabetical */
  const sortedIndustries = [...filteredIndustries].sort((a, b) => {
    const aSelected = filters.industries.includes(a) ? 1 : 0;
    const bSelected = filters.industries.includes(b) ? 1 : 0;
    if (aSelected !== bSelected) return bSelected - aSelected;
    const aAi = isAiHighlightedIndustry(a) ? 1 : 0;
    const bAi = isAiHighlightedIndustry(b) ? 1 : 0;
    if (aAi !== bAi) return bAi - aAi;
    return 0;
  });

  const filteredCountries = countrySearch
    ? COUNTRIES.filter(c => c.toLowerCase().includes(countrySearch.toLowerCase()))
    : COUNTRIES;

  /* ── section header helper ──────────────────────────────────────────── */
  const SectionHeader = ({ id, title }: { id: string; title: string }) => {
    const count = sectionActiveCount(id, filters);
    const isCollapsed = !!collapsed[id];
    return (
      <button
        type="button"
        className="filter-section-toggle"
        onClick={() => toggleSection(id)}
        aria-expanded={!isCollapsed}
      >
        <span className="filter-section-title">
          {title}
          {count > 0 && <span className="filter-section-badge">{count}</span>}
        </span>
        <span className={`filter-chevron${isCollapsed ? ' filter-chevron--closed' : ''}`}>
          ‹
        </span>
      </button>
    );
  };

  return (
    <div className="filter-panel">

      {/* ── Active filter summary ───────────────────────────────────── */}
      {totalActive > 0 && (
        <div className="filter-active-summary">
          <span>{totalActive} filter{totalActive !== 1 ? 's' : ''} active</span>
          <button type="button" className="filter-active-clear" onClick={onClear}>
            Clear all
          </button>
        </div>
      )}

      {/* AI highlights header */}
      {hasAiHighlights && (
        <div className="ai-filter-banner">
          <span className="ai-filter-banner-label">✦ AI detected intent</span>
          <button className="ai-filter-clear-btn" onClick={onClearAiFilters}>
            Clear
          </button>
        </div>
      )}

      {/* ── Industry ────────────────────────────────────────────────── */}
      <div className="filter-group">
        <SectionHeader id="industry" title="Industry" />
        {!collapsed['industry'] && (
          <>
            <input
              type="text"
              className="filter-search-input"
              placeholder="Search industries…"
              value={industrySearch}
              onChange={e => setIndustrySearch(e.target.value)}
            />
            <div className="filter-scroll-list">
              {sortedIndustries.map(ind => {
                const highlighted = isAiHighlightedIndustry(ind);
                return (
                  <label key={ind} className={`filter-checkbox${highlighted ? ' filter-checkbox--ai-active' : ''}`}>
                    <input
                      type="checkbox"
                      checked={filters.industries.includes(ind)}
                      onChange={() =>
                        onFiltersChange({ ...filters, industries: toggle(filters.industries, ind) })
                      }
                    />
                    <span>{ind}</span>
                    {highlighted && <span className="ai-badge">✦ AI</span>}
                  </label>
                );
              })}
              {sortedIndustries.length === 0 && (
                <span className="filter-no-match">No matching industries</span>
              )}
            </div>
          </>
        )}
      </div>

      {/* ── Company Size (pill chips) ───────────────────────────────── */}
      <div className="filter-group">
        <SectionHeader id="size" title="Company Size" />
        {!collapsed['size'] && (
          <div className="size-chips">
            {SIZE_OPTIONS.map(({ label, value }) => {
              const active = filters.sizeRanges.includes(value);
              return (
                <button
                  key={value}
                  type="button"
                  className={`size-chip${active ? ' size-chip--active' : ''}`}
                  onClick={() =>
                    onFiltersChange({ ...filters, sizeRanges: toggle(filters.sizeRanges, value) })
                  }
                >
                  {label}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Location (searchable country) ───────────────────────────── */}
      <div className="filter-group">
        <SectionHeader id="location" title="Location" />
        {!collapsed['location'] && (
          <>
            <div className="country-dropdown" ref={countryRef}>
              <input
                type="text"
                className={`filter-input country-search-input${
                  isAiHighlightedCountry(filters.country || aiHighlights?.country || '')
                    ? ' filter-select--ai-active'
                    : ''
                }`}
                placeholder="Search countries…"
                value={countryOpen ? countrySearch : (filters.country || '')}
                onFocus={() => {
                  setCountryOpen(true);
                  setCountrySearch(filters.country || '');
                }}
                onChange={e => {
                  setCountrySearch(e.target.value);
                  if (!countryOpen) setCountryOpen(true);
                }}
              />
              {filters.country && !countryOpen && (
                <button
                  type="button"
                  className="country-clear-btn"
                  onClick={() => {
                    onFiltersChange({ ...filters, country: '' });
                    setCountrySearch('');
                  }}
                >
                  ×
                </button>
              )}
              {countryOpen && (
                <div className="country-dropdown-list">
                  <div
                    className={`country-dropdown-item${!filters.country ? ' country-dropdown-item--active' : ''}`}
                    onClick={() => {
                      onFiltersChange({ ...filters, country: '' });
                      setCountrySearch('');
                      setCountryOpen(false);
                    }}
                  >
                    All Countries
                  </div>
                  {filteredCountries.map(c => (
                    <div
                      key={c}
                      className={`country-dropdown-item${
                        filters.country === c ? ' country-dropdown-item--active' : ''
                      }`}
                      onClick={() => {
                        onFiltersChange({ ...filters, country: c });
                        setCountrySearch('');
                        setCountryOpen(false);
                      }}
                    >
                      {c}
                    </div>
                  ))}
                  {filteredCountries.length === 0 && (
                    <div className="country-dropdown-empty">No matching countries</div>
                  )}
                </div>
              )}
            </div>
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
          </>
        )}
      </div>

      {/* ── Founding Year ───────────────────────────────────────────── */}
      <div className="filter-group">
        <SectionHeader id="year" title="Founding Year" />
        {!collapsed['year'] && (
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
        )}
      </div>

      {/* ── Tags (placeholder) ──────────────────────────────────────── */}
      <div className="filter-group filter-group-last">
        <SectionHeader id="tags" title="Tags" />
        {!collapsed['tags'] && (
          <>
            <label className="filter-checkbox filter-disabled">
              <input type="checkbox" disabled />
              <span>My Tags</span>
            </label>
            <label className="filter-checkbox filter-disabled" style={{ marginTop: 4 }}>
              <input type="checkbox" disabled />
              <span>Shared Lists</span>
            </label>
            <p className="filter-hint">Tagging coming soon</p>
          </>
        )}
      </div>

      {/* ── Buttons ─────────────────────────────────────────────────── */}
      <div className="filter-buttons">
        <button onClick={onClear} className="btn btn-secondary">Clear All</button>
        <button onClick={onApply} disabled={loading} className="btn btn-primary">
          {loading ? 'Searching…' : 'Apply Filters'}
        </button>
      </div>
    </div>
  );
}
