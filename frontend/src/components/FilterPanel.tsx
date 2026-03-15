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

const SIZE_OPTIONS = [
  { label: 'Micro (1–10)', value: '1 - 10' },
  { label: 'Small (11–50)', value: '11 - 50' },
  { label: 'Small (51–200)', value: '51 - 200' },
  { label: 'Medium (201–500)', value: '201 - 500' },
  { label: 'Medium (501–1000)', value: '501 - 1000' },
  { label: 'Large (1001–5000)', value: '1001 - 5000' },
  { label: 'Large (5001–10000)', value: '5001 - 10000' },
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
