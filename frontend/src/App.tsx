import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
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
  // ── Continents / Regions ──
  [/\b(europe)\b/i, 'Europe'],
  [/\b(asia)\b/i, 'Asia'],
  [/\b(africa)\b/i, 'Africa'],
  [/\b(south america)\b/i, 'South America'],
  [/\b(north america)\b/i, 'North America'],
  [/\b(latin america)\b/i, 'Latin America'],
  [/\b(middle east)\b/i, 'Middle East'],
  [/\b(southeast asia)\b/i, 'Southeast Asia'],
  [/\b(east asia)\b/i, 'East Asia'],
  [/\b(central asia)\b/i, 'Central Asia'],
  [/\b(oceania|pacific islands)\b/i, 'Oceania'],
  [/\b(scandinavia|nordic)\b/i, 'Scandinavia'],
  [/\b(caribbean)\b/i, 'Caribbean'],
  [/\b(baltics)\b/i, 'Baltics'],
  [/\b(balkans)\b/i, 'Balkans'],
  [/\b(mena)\b/i, 'MENA'],

  // ── Countries (A–Z) ──
  [/\b(afghanistan)\b/i, 'Afghanistan'],
  [/\b(albania)\b/i, 'Albania'],
  [/\b(algeria)\b/i, 'Algeria'],
  [/\b(andorra)\b/i, 'Andorra'],
  [/\b(angola)\b/i, 'Angola'],
  [/\b(antigua)\b/i, 'Antigua and Barbuda'],
  [/\b(argentin[ae])\b/i, 'Argentina'],
  [/\b(armenia)\b/i, 'Armenia'],
  [/\b(australia|aus)\b/i, 'Australia'],
  [/\b(austria)\b/i, 'Austria'],
  [/\b(azerbaijan)\b/i, 'Azerbaijan'],
  [/\b(bahamas)\b/i, 'Bahamas'],
  [/\b(bahrain)\b/i, 'Bahrain'],
  [/\b(bangladesh)\b/i, 'Bangladesh'],
  [/\b(barbados)\b/i, 'Barbados'],
  [/\b(belarus)\b/i, 'Belarus'],
  [/\b(belgium)\b/i, 'Belgium'],
  [/\b(belize)\b/i, 'Belize'],
  [/\b(benin)\b/i, 'Benin'],
  [/\b(bermuda)\b/i, 'Bermuda'],
  [/\b(bhutan)\b/i, 'Bhutan'],
  [/\b(bolivia)\b/i, 'Bolivia'],
  [/\b(bosnia)\b/i, 'Bosnia and Herzegovina'],
  [/\b(botswana)\b/i, 'Botswana'],
  [/\b(brazil|brasil)\b/i, 'Brazil'],
  [/\b(brunei)\b/i, 'Brunei'],
  [/\b(bulgaria)\b/i, 'Bulgaria'],
  [/\b(burkina faso)\b/i, 'Burkina Faso'],
  [/\b(burundi)\b/i, 'Burundi'],
  [/\b(cambodia)\b/i, 'Cambodia'],
  [/\b(cameroon)\b/i, 'Cameroon'],
  [/\b(canada)\b/i, 'Canada'],
  [/\b(cape verde|cabo verde)\b/i, 'Cape Verde'],
  [/\b(chad)\b/i, 'Chad'],
  [/\b(chile)\b/i, 'Chile'],
  [/\b(china|prc)\b/i, 'China'],
  [/\b(colombia)\b/i, 'Colombia'],
  [/\b(congo)\b/i, 'Congo'],
  [/\b(costa rica)\b/i, 'Costa Rica'],
  [/\b(croatia)\b/i, 'Croatia'],
  [/\b(cuba)\b/i, 'Cuba'],
  [/\b(cyprus)\b/i, 'Cyprus'],
  [/\b(czech|czechia)\b/i, 'Czechia'],
  [/\b(denmark)\b/i, 'Denmark'],
  [/\b(djibouti)\b/i, 'Djibouti'],
  [/\b(dominican republic)\b/i, 'Dominican Republic'],
  [/\b(ecuador)\b/i, 'Ecuador'],
  [/\b(egypt)\b/i, 'Egypt'],
  [/\b(el salvador)\b/i, 'El Salvador'],
  [/\b(eritrea)\b/i, 'Eritrea'],
  [/\b(estonia)\b/i, 'Estonia'],
  [/\b(ethiopia)\b/i, 'Ethiopia'],
  [/\b(fiji)\b/i, 'Fiji'],
  [/\b(finland)\b/i, 'Finland'],
  [/\b(france)\b/i, 'France'],
  [/\b(gabon)\b/i, 'Gabon'],
  [/\b(gambia)\b/i, 'Gambia'],
  [/\b(georgia)\b/i, 'Georgia'],
  [/\b(germany|deutschland)\b/i, 'Germany'],
  [/\b(ghana)\b/i, 'Ghana'],
  [/\b(greece)\b/i, 'Greece'],
  [/\b(greenland)\b/i, 'Greenland'],
  [/\b(guatemala)\b/i, 'Guatemala'],
  [/\b(guinea)\b/i, 'Guinea'],
  [/\b(guyana)\b/i, 'Guyana'],
  [/\b(haiti)\b/i, 'Haiti'],
  [/\b(honduras)\b/i, 'Honduras'],
  [/\b(hong kong|hk)\b/i, 'Hong Kong'],
  [/\b(hungary)\b/i, 'Hungary'],
  [/\b(iceland)\b/i, 'Iceland'],
  [/\b(india)\b/i, 'India'],
  [/\b(indonesia)\b/i, 'Indonesia'],
  [/\b(iran)\b/i, 'Iran'],
  [/\b(iraq)\b/i, 'Iraq'],
  [/\b(ireland)\b/i, 'Ireland'],
  [/\b(israel)\b/i, 'Israel'],
  [/\b(italy)\b/i, 'Italy'],
  [/\b(ivory coast)\b/i, "Côte d'Ivoire"],
  [/\b(jamaica)\b/i, 'Jamaica'],
  [/\b(japan)\b/i, 'Japan'],
  [/\b(jordan)\b/i, 'Jordan'],
  [/\b(kazakhstan)\b/i, 'Kazakhstan'],
  [/\b(kenya)\b/i, 'Kenya'],
  [/\b(kosovo)\b/i, 'Kosovo'],
  [/\b(kuwait)\b/i, 'Kuwait'],
  [/\b(kyrgyzstan)\b/i, 'Kyrgyzstan'],
  [/\b(laos)\b/i, 'Laos'],
  [/\b(latvia)\b/i, 'Latvia'],
  [/\b(lebanon)\b/i, 'Lebanon'],
  [/\b(lesotho)\b/i, 'Lesotho'],
  [/\b(liberia)\b/i, 'Liberia'],
  [/\b(libya)\b/i, 'Libya'],
  [/\b(liechtenstein)\b/i, 'Liechtenstein'],
  [/\b(lithuania)\b/i, 'Lithuania'],
  [/\b(luxembourg)\b/i, 'Luxembourg'],
  [/\b(macau|macao)\b/i, 'Macau'],
  [/\b(macedonia)\b/i, 'Macedonia'],
  [/\b(madagascar)\b/i, 'Madagascar'],
  [/\b(malawi)\b/i, 'Malawi'],
  [/\b(malaysia)\b/i, 'Malaysia'],
  [/\b(maldives)\b/i, 'Maldives'],
  [/\b(mali)\b/i, 'Mali'],
  [/\b(malta)\b/i, 'Malta'],
  [/\b(mauritius)\b/i, 'Mauritius'],
  [/\b(mexico)\b/i, 'Mexico'],
  [/\b(moldova)\b/i, 'Moldova'],
  [/\b(monaco)\b/i, 'Monaco'],
  [/\b(mongolia)\b/i, 'Mongolia'],
  [/\b(montenegro)\b/i, 'Montenegro'],
  [/\b(morocco)\b/i, 'Morocco'],
  [/\b(mozambique)\b/i, 'Mozambique'],
  [/\b(myanmar|burma)\b/i, 'Myanmar'],
  [/\b(namibia)\b/i, 'Namibia'],
  [/\b(nepal)\b/i, 'Nepal'],
  [/\b(netherlands|holland)\b/i, 'Netherlands'],
  [/\b(new zealand|nz)\b/i, 'New Zealand'],
  [/\b(nicaragua)\b/i, 'Nicaragua'],
  [/\b(niger)\b/i, 'Niger'],
  [/\b(nigeria)\b/i, 'Nigeria'],
  [/\b(north korea|dprk)\b/i, 'North Korea'],
  [/\b(norway)\b/i, 'Norway'],
  [/\b(oman)\b/i, 'Oman'],
  [/\b(pakistan)\b/i, 'Pakistan'],
  [/\b(palestine)\b/i, 'Palestine'],
  [/\b(panama)\b/i, 'Panama'],
  [/\b(papua new guinea)\b/i, 'Papua New Guinea'],
  [/\b(paraguay)\b/i, 'Paraguay'],
  [/\b(peru)\b/i, 'Peru'],
  [/\b(philippines)\b/i, 'Philippines'],
  [/\b(poland)\b/i, 'Poland'],
  [/\b(portugal)\b/i, 'Portugal'],
  [/\b(puerto rico)\b/i, 'Puerto Rico'],
  [/\b(qatar)\b/i, 'Qatar'],
  [/\b(romania)\b/i, 'Romania'],
  [/\b(russia|russian federation)\b/i, 'Russia'],
  [/\b(rwanda)\b/i, 'Rwanda'],
  [/\b(samoa)\b/i, 'Samoa'],
  [/\b(saudi arabia|ksa)\b/i, 'Saudi Arabia'],
  [/\b(senegal)\b/i, 'Senegal'],
  [/\b(serbia)\b/i, 'Serbia'],
  [/\b(seychelles)\b/i, 'Seychelles'],
  [/\b(sierra leone)\b/i, 'Sierra Leone'],
  [/\b(singapore)\b/i, 'Singapore'],
  [/\b(slovakia)\b/i, 'Slovakia'],
  [/\b(slovenia)\b/i, 'Slovenia'],
  [/\b(somalia)\b/i, 'Somalia'],
  [/\b(south africa)\b/i, 'South Africa'],
  [/\b(south korea|korea)\b/i, 'South Korea'],
  [/\b(south sudan)\b/i, 'South Sudan'],
  [/\b(spain)\b/i, 'Spain'],
  [/\b(sri lanka)\b/i, 'Sri Lanka'],
  [/\b(sudan)\b/i, 'Sudan'],
  [/\b(suriname)\b/i, 'Suriname'],
  [/\b(sweden)\b/i, 'Sweden'],
  [/\b(switzerland)\b/i, 'Switzerland'],
  [/\b(syria)\b/i, 'Syria'],
  [/\b(taiwan)\b/i, 'Taiwan'],
  [/\b(tajikistan)\b/i, 'Tajikistan'],
  [/\b(tanzania)\b/i, 'Tanzania'],
  [/\b(thailand)\b/i, 'Thailand'],
  [/\b(togo)\b/i, 'Togo'],
  [/\b(trinidad)\b/i, 'Trinidad and Tobago'],
  [/\b(tunisia)\b/i, 'Tunisia'],
  [/\b(turkey|türkiye|turkiye)\b/i, 'Turkey'],
  [/\b(turkmenistan)\b/i, 'Turkmenistan'],
  [/\b(uganda)\b/i, 'Uganda'],
  [/\b(ukraine)\b/i, 'Ukraine'],
  [/\b(uae|united arab emirates|emirates|dubai|abu dhabi)\b/i, 'United Arab Emirates'],
  [/\b(uk|united kingdom|britain|england)\b/i, 'United Kingdom'],
  [/\b(usa|united states|america)\b/i, 'United States'],
  [/\b(uruguay)\b/i, 'Uruguay'],
  [/\b(uzbekistan)\b/i, 'Uzbekistan'],
  [/\b(venezuela)\b/i, 'Venezuela'],
  [/\b(vietnam|viet nam)\b/i, 'Vietnam'],
  [/\b(yemen)\b/i, 'Yemen'],
  [/\b(zambia)\b/i, 'Zambia'],
  [/\b(zimbabwe)\b/i, 'Zimbabwe'],

  // ── US States ──
  [/\b(alabama)\b/i, 'Alabama'],
  [/\b(alaska)\b/i, 'Alaska'],
  [/\b(arizona)\b/i, 'Arizona'],
  [/\b(arkansas)\b/i, 'Arkansas'],
  [/\b(california|ca)\b/i, 'California'],
  [/\b(colorado)\b/i, 'Colorado'],
  [/\b(connecticut)\b/i, 'Connecticut'],
  [/\b(delaware)\b/i, 'Delaware'],
  [/\b(florida)\b/i, 'Florida'],
  [/\b(hawaii)\b/i, 'Hawaii'],
  [/\b(idaho)\b/i, 'Idaho'],
  [/\b(illinois)\b/i, 'Illinois'],
  [/\b(indiana)\b/i, 'Indiana'],
  [/\b(iowa)\b/i, 'Iowa'],
  [/\b(kansas)\b/i, 'Kansas'],
  [/\b(kentucky)\b/i, 'Kentucky'],
  [/\b(louisiana)\b/i, 'Louisiana'],
  [/\b(maine)\b/i, 'Maine'],
  [/\b(maryland)\b/i, 'Maryland'],
  [/\b(massachusetts)\b/i, 'Massachusetts'],
  [/\b(michigan)\b/i, 'Michigan'],
  [/\b(minnesota)\b/i, 'Minnesota'],
  [/\b(mississippi)\b/i, 'Mississippi'],
  [/\b(missouri)\b/i, 'Missouri'],
  [/\b(montana)\b/i, 'Montana'],
  [/\b(nebraska)\b/i, 'Nebraska'],
  [/\b(nevada)\b/i, 'Nevada'],
  [/\b(new hampshire)\b/i, 'New Hampshire'],
  [/\b(new jersey)\b/i, 'New Jersey'],
  [/\b(new mexico)\b/i, 'New Mexico'],
  [/\b(new york|ny|nyc)\b/i, 'New York'],
  [/\b(north carolina)\b/i, 'North Carolina'],
  [/\b(north dakota)\b/i, 'North Dakota'],
  [/\b(ohio)\b/i, 'Ohio'],
  [/\b(oklahoma)\b/i, 'Oklahoma'],
  [/\b(oregon)\b/i, 'Oregon'],
  [/\b(pennsylvania)\b/i, 'Pennsylvania'],
  [/\b(rhode island)\b/i, 'Rhode Island'],
  [/\b(south carolina)\b/i, 'South Carolina'],
  [/\b(south dakota)\b/i, 'South Dakota'],
  [/\b(tennessee)\b/i, 'Tennessee'],
  [/\b(texas|tx)\b/i, 'Texas'],
  [/\b(utah)\b/i, 'Utah'],
  [/\b(vermont)\b/i, 'Vermont'],
  [/\b(virginia)\b/i, 'Virginia'],
  [/\b(washington)\b/i, 'Washington'],
  [/\b(west virginia)\b/i, 'West Virginia'],
  [/\b(wisconsin)\b/i, 'Wisconsin'],
  [/\b(wyoming)\b/i, 'Wyoming'],

  // ── Major Global Cities ──
  [/\b(london)\b/i, 'London'],
  [/\b(paris)\b/i, 'Paris'],
  [/\b(berlin)\b/i, 'Berlin'],
  [/\b(tokyo)\b/i, 'Tokyo'],
  [/\b(shanghai)\b/i, 'Shanghai'],
  [/\b(beijing)\b/i, 'Beijing'],
  [/\b(shenzhen)\b/i, 'Shenzhen'],
  [/\b(mumbai|bombay)\b/i, 'Mumbai'],
  [/\b(bangalore|bengaluru)\b/i, 'Bangalore'],
  [/\b(delhi)\b/i, 'Delhi'],
  [/\b(hyderabad)\b/i, 'Hyderabad'],
  [/\b(chennai|madras)\b/i, 'Chennai'],
  [/\b(pune)\b/i, 'Pune'],
  [/\b(kolkata|calcutta)\b/i, 'Kolkata'],
  [/\b(sydney)\b/i, 'Sydney'],
  [/\b(melbourne)\b/i, 'Melbourne'],
  [/\b(brisbane)\b/i, 'Brisbane'],
  [/\b(perth)\b/i, 'Perth'],
  [/\b(auckland)\b/i, 'Auckland'],
  [/\b(toronto)\b/i, 'Toronto'],
  [/\b(vancouver)\b/i, 'Vancouver'],
  [/\b(montreal)\b/i, 'Montreal'],
  [/\b(san francisco|sf)\b/i, 'San Francisco'],
  [/\b(los angeles|la)\b/i, 'Los Angeles'],
  [/\b(seattle)\b/i, 'Seattle'],
  [/\b(boston)\b/i, 'Boston'],
  [/\b(chicago)\b/i, 'Chicago'],
  [/\b(houston)\b/i, 'Houston'],
  [/\b(dallas)\b/i, 'Dallas'],
  [/\b(austin)\b/i, 'Austin'],
  [/\b(denver)\b/i, 'Denver'],
  [/\b(atlanta)\b/i, 'Atlanta'],
  [/\b(miami)\b/i, 'Miami'],
  [/\b(phoenix)\b/i, 'Phoenix'],
  [/\b(detroit)\b/i, 'Detroit'],
  [/\b(minneapolis)\b/i, 'Minneapolis'],
  [/\b(pittsburgh)\b/i, 'Pittsburgh'],
  [/\b(portland)\b/i, 'Portland'],
  [/\b(san diego)\b/i, 'San Diego'],
  [/\b(san jose)\b/i, 'San Jose'],
  [/\b(silicon valley)\b/i, 'Silicon Valley'],
  [/\b(amsterdam)\b/i, 'Amsterdam'],
  [/\b(barcelona)\b/i, 'Barcelona'],
  [/\b(madrid)\b/i, 'Madrid'],
  [/\b(stockholm)\b/i, 'Stockholm'],
  [/\b(oslo)\b/i, 'Oslo'],
  [/\b(copenhagen)\b/i, 'Copenhagen'],
  [/\b(helsinki)\b/i, 'Helsinki'],
  [/\b(dublin)\b/i, 'Dublin'],
  [/\b(zurich)\b/i, 'Zurich'],
  [/\b(geneva)\b/i, 'Geneva'],
  [/\b(munich|münchen)\b/i, 'Munich'],
  [/\b(frankfurt)\b/i, 'Frankfurt'],
  [/\b(hamburg)\b/i, 'Hamburg'],
  [/\b(vienna)\b/i, 'Vienna'],
  [/\b(brussels)\b/i, 'Brussels'],
  [/\b(lisbon)\b/i, 'Lisbon'],
  [/\b(rome)\b/i, 'Rome'],
  [/\b(milan)\b/i, 'Milan'],
  [/\b(prague)\b/i, 'Prague'],
  [/\b(warsaw)\b/i, 'Warsaw'],
  [/\b(budapest)\b/i, 'Budapest'],
  [/\b(bucharest)\b/i, 'Bucharest'],
  [/\b(istanbul)\b/i, 'Istanbul'],
  [/\b(tel aviv)\b/i, 'Tel Aviv'],
  [/\b(riyadh)\b/i, 'Riyadh'],
  [/\b(jeddah)\b/i, 'Jeddah'],
  [/\b(doha)\b/i, 'Doha'],
  [/\b(muscat)\b/i, 'Muscat'],
  [/\b(cairo)\b/i, 'Cairo'],
  [/\b(nairobi)\b/i, 'Nairobi'],
  [/\b(lagos)\b/i, 'Lagos'],
  [/\b(cape town)\b/i, 'Cape Town'],
  [/\b(johannesburg)\b/i, 'Johannesburg'],
  [/\b(accra)\b/i, 'Accra'],
  [/\b(casablanca)\b/i, 'Casablanca'],
  [/\b(s[aã]o paulo)\b/i, 'São Paulo'],
  [/\b(rio de janeiro)\b/i, 'Rio de Janeiro'],
  [/\b(buenos aires)\b/i, 'Buenos Aires'],
  [/\b(bogot[aá])\b/i, 'Bogotá'],
  [/\b(lima)\b/i, 'Lima'],
  [/\b(santiago)\b/i, 'Santiago'],
  [/\b(mexico city)\b/i, 'Mexico City'],
  [/\b(kuala lumpur|kl)\b/i, 'Kuala Lumpur'],
  [/\b(bangkok)\b/i, 'Bangkok'],
  [/\b(jakarta)\b/i, 'Jakarta'],
  [/\b(manila)\b/i, 'Manila'],
  [/\b(ho chi minh)\b/i, 'Ho Chi Minh City'],
  [/\b(hanoi)\b/i, 'Hanoi'],
  [/\b(seoul)\b/i, 'Seoul'],
  [/\b(taipei)\b/i, 'Taipei'],
  [/\b(osaka)\b/i, 'Osaka'],
];

const IND_MAP: Array<[RegExp, string]> = [
  // ── Technology & Computing ──
  [/\b(tech|technology|software|saas|it services)\b/i, 'Technology'],
  [/\b(computer software|software engineering)\b/i, 'Computer Software'],
  [/\b(computer hardware|hardware)\b/i, 'Computer Hardware'],
  [/\b(computer networking|networking)\b/i, 'Computer Networking'],
  [/\b(computer games|video games|gaming)\b/i, 'Computer Games'],
  [/\b(cybersecurity|infosec|computer.*security|network security)\b/i, 'Cybersecurity'],
  [/\b(semiconductors?|chips?)\b/i, 'Semiconductors'],
  [/\b(nanotech(nology)?)\b/i, 'Nanotechnology'],
  [/\b(information services|data services)\b/i, 'Information Services'],
  [/\b(wireless|mobile tech)\b/i, 'Wireless'],
  [/\b(telecom(munications)?|broadband)\b/i, 'Telecommunications'],
  [/\b(internet|web|online|digital)\b/i, 'Internet'],
  [/\b(industrial automation|automation|robotics)\b/i, 'Industrial Automation'],
  [/\b(e-?learning|edtech|online learning)\b/i, 'E-Learning'],
  [/\b(ai|artificial intelligence)\b/i, 'AI / ML'],
  [/\b(machine learning|ml|deep learning)\b/i, 'AI / ML'],
  [/\b(cloud computing|cloud)\b/i, 'Cloud Computing'],
  [/\b(blockchain|crypto|web3)\b/i, 'Blockchain'],

  // ── Finance & Banking ──
  [/\b(fintech|financial tech)\b/i, 'Fintech'],
  [/\b(financial services|finance)\b/i, 'Financial Services'],
  [/\b(banking|banks?)\b/i, 'Banking'],
  [/\b(insurance|insurtech)\b/i, 'Insurance'],
  [/\b(investment banking)\b/i, 'Investment Banking'],
  [/\b(investment management|asset management|wealth management)\b/i, 'Investment Management'],
  [/\b(capital markets|trading|equities|securities)\b/i, 'Capital Markets'],
  [/\b(venture capital|vc|private equity)\b/i, 'Venture Capital & Private Equity'],
  [/\b(accounting|audit)\b/i, 'Accounting'],

  // ── Healthcare & Life Sciences ──
  [/\b(health\s*care|medical|hospital)\b/i, 'Healthcare'],
  [/\b(biotech(nology)?|life sciences)\b/i, 'Biotechnology'],
  [/\b(pharma(ceuticals)?|drugs?)\b/i, 'Pharmaceuticals'],
  [/\b(medical devices?|medtech)\b/i, 'Medical Devices'],
  [/\b(medical practice|doctors?|clinical)\b/i, 'Medical Practice'],
  [/\b(mental health|psychiatry|psychology|therapy)\b/i, 'Mental Health Care'],
  [/\b(wellness|fitness|health.*wellness)\b/i, 'Health, Wellness and Fitness'],
  [/\b(alternative medicine|holistic|naturopathy)\b/i, 'Alternative Medicine'],
  [/\b(veterinary|vet|animal health)\b/i, 'Veterinary'],

  // ── Energy & Environment ──
  [/\b(oil|gas|petroleum|energy)\b/i, 'Oil & Energy'],
  [/\b(renewable|clean energy|solar|wind|green energy)\b/i, 'Renewables & Environment'],
  [/\b(utilities|power|water.*utility)\b/i, 'Utilities'],
  [/\b(environmental services|environment|sustainability)\b/i, 'Environmental Services'],
  [/\b(chemicals?)\b/i, 'Chemicals'],
  [/\b(mining|metals?|resources)\b/i, 'Mining & Metals'],
  [/\b(plastics?|polymer)\b/i, 'Plastics'],
  [/\b(paper|forest products|timber|pulp)\b/i, 'Paper & Forest Products'],

  // ── Retail & Consumer ──
  [/\b(retail|e-?commerce|shopping)\b/i, 'Retail'],
  [/\b(supermarket|grocery)\b/i, 'Supermarkets'],
  [/\b(consumer goods|fmcg)\b/i, 'Consumer Goods'],
  [/\b(consumer electronics|gadgets)\b/i, 'Consumer Electronics'],
  [/\b(consumer services)\b/i, 'Consumer Services'],
  [/\b(luxury|jewelry|high.?end)\b/i, 'Luxury Goods & Jewelry'],
  [/\b(cosmetics?|beauty|skincare)\b/i, 'Cosmetics'],
  [/\b(apparel|fashion|clothing)\b/i, 'Apparel & Fashion'],
  [/\b(sporting goods)\b/i, 'Sporting Goods'],

  // ── Manufacturing & Engineering ──
  [/\b(manufacturing|industrial)\b/i, 'Manufacturing'],
  [/\b(machinery|equipment)\b/i, 'Machinery'],
  [/\b(automotive|cars?|vehicles?)\b/i, 'Automotive'],
  [/\b(aerospace|aviation|aircraft)\b/i, 'Aviation & Aerospace'],
  [/\b(defense|military|defence)\b/i, 'Defense & Space'],
  [/\b(shipbuilding|naval|maritime)\b/i, 'Shipbuilding'],
  [/\b(electrical.*manufacturing|electronic.*manufacturing)\b/i, 'Electrical/Electronic Manufacturing'],
  [/\b(glass|ceramics?|concrete)\b/i, 'Glass, Ceramics & Concrete'],
  [/\b(packaging|containers?)\b/i, 'Packaging and Containers'],
  [/\b(textiles?)\b/i, 'Textiles'],
  [/\b(building materials)\b/i, 'Building Materials'],
  [/\b(furniture)\b/i, 'Furniture'],
  [/\b(printing|print)\b/i, 'Printing'],

  // ── Construction & Real Estate ──
  [/\b(construction)\b/i, 'Construction'],
  [/\b(real estate|property|realty)\b/i, 'Real Estate'],
  [/\b(commercial real estate|cre)\b/i, 'Commercial Real Estate'],
  [/\b(architecture|planning)\b/i, 'Architecture & Planning'],
  [/\b(civil engineering)\b/i, 'Civil Engineering'],
  [/\b(facilities services|facilities management)\b/i, 'Facilities Services'],

  // ── Education ──
  [/\b(education|university|universities|school|college)\b/i, 'Education'],
  [/\b(higher education|academia)\b/i, 'Higher Education'],
  [/\b(k-?12|primary.*education|secondary.*education)\b/i, 'Primary/Secondary Education'],
  [/\b(training|coaching|professional development)\b/i, 'Professional Training & Coaching'],
  [/\b(libraries?|archives?)\b/i, 'Libraries'],

  // ── Professional Services ──
  [/\b(consulting|advisory|consultancy|management consulting)\b/i, 'Consulting'],
  [/\b(law|legal|lawyers?|attorneys?|solicitors?)\b/i, 'Legal'],
  [/\b(staffing|recruiting|recruitment|talent acquisition)\b/i, 'Staffing and Recruiting'],
  [/\b(human resources|hr|people ops)\b/i, 'Human Resources'],
  [/\b(market research|analytics|insights)\b/i, 'Market Research'],
  [/\b(outsourcing|offshoring|bpo)\b/i, 'Outsourcing/Offshoring'],
  [/\b(translation|localization|language services)\b/i, 'Translation and Localization'],
  [/\b(graphic design|branding|visual design)\b/i, 'Graphic Design'],
  [/\b(design|ux|ui|product design)\b/i, 'Design'],
  [/\b(business supplies)\b/i, 'Business Supplies and Equipment'],
  [/\b(events?.*services?|conferences?|exhibitions?)\b/i, 'Events Services'],
  [/\b(security.*investigations?|guarding)\b/i, 'Security and Investigations'],

  // ── Marketing & Media ──
  [/\b(marketing|advertising|digital marketing)\b/i, 'Marketing and Advertising'],
  [/\b(public relations|pr|communications)\b/i, 'Public Relations and Communications'],
  [/\b(media|entertainment|content)\b/i, 'Media'],
  [/\b(broadcast|tv|radio)\b/i, 'Broadcast Media'],
  [/\b(online media|digital media)\b/i, 'Online Media'],
  [/\b(newspapers?|journalism)\b/i, 'Newspapers'],
  [/\b(publishing|books?)\b/i, 'Publishing'],
  [/\b(film|movies?|cinema|motion pictures)\b/i, 'Motion Pictures and Film'],
  [/\b(music|record labels?)\b/i, 'Music'],
  [/\b(performing arts|theatre|theater|dance|opera)\b/i, 'Performing Arts'],
  [/\b(fine art|galleries?|visual arts?)\b/i, 'Fine Art'],
  [/\b(animation|vfx|cgi)\b/i, 'Animation'],
  [/\b(photography)\b/i, 'Photography'],
  [/\b(writing|copywriting|editing)\b/i, 'Writing and Editing'],

  // ── Logistics & Transportation ──
  [/\b(logistics|supply chain)\b/i, 'Logistics'],
  [/\b(transportation|trucking|freight)\b/i, 'Transportation'],
  [/\b(warehousing|distribution|fulfillment)\b/i, 'Warehousing'],
  [/\b(airlines?|airports?)\b/i, 'Airlines/Aviation'],
  [/\b(shipping|ports?|maritime)\b/i, 'Maritime'],
  [/\b(import.*export|trade)\b/i, 'Import and Export'],
  [/\b(delivery|courier|package)\b/i, 'Package/Freight Delivery'],
  [/\b(railroad|rail)\b/i, 'Railroad Manufacture'],

  // ── Food & Hospitality ──
  [/\b(food|beverages?|f&b)\b/i, 'Food & Beverages'],
  [/\b(restaurants?|dining)\b/i, 'Restaurants'],
  [/\b(food production|food processing|food manufacturing)\b/i, 'Food Production'],
  [/\b(hospitality|hotels?)\b/i, 'Hospitality'],
  [/\b(travel|tourism|leisure)\b/i, 'Leisure, Travel & Tourism'],
  [/\b(dairy)\b/i, 'Dairy'],
  [/\b(wine|spirits?|alcohol|distiller)\b/i, 'Wine and Spirits'],
  [/\b(gambling|casinos?|betting)\b/i, 'Gambling & Casinos'],
  [/\b(recreation)\b/i, 'Recreational Facilities and Services'],

  // ── Government & Public Sector ──
  [/\b(government|public sector|administration)\b/i, 'Government'],
  [/\b(law enforcement|police)\b/i, 'Law Enforcement'],
  [/\b(public safety|emergency services)\b/i, 'Public Safety'],
  [/\b(public policy|regulatory)\b/i, 'Public Policy'],
  [/\b(international affairs|diplomacy|foreign affairs)\b/i, 'International Affairs'],

  // ── Non-Profit & Social ──
  [/\b(non-?profit|ngo|charity)\b/i, 'Non-Profit'],
  [/\b(philanthropy|foundations?|giving)\b/i, 'Philanthropy'],
  [/\b(fundraising|crowdfunding)\b/i, 'Fund-Raising'],
  [/\b(civic|community|social organization)\b/i, 'Civic & Social Organization'],
  [/\b(religious|church|mosque|temple|faith)\b/i, 'Religious Institutions'],
  [/\b(think tanks?|policy research)\b/i, 'Think Tanks'],

  // ── Agriculture ──
  [/\b(farming|agriculture|crops?)\b/i, 'Farming'],
  [/\b(ranching|livestock)\b/i, 'Ranching'],
  [/\b(fishery|aquaculture|seafood)\b/i, 'Fishery'],
  [/\b(tobacco)\b/i, 'Tobacco'],

  // ── Other ──
  [/\b(research|r&d)\b/i, 'Research'],
  [/\b(sports?|athletics)\b/i, 'Sports'],
  [/\b(museums?|cultural|heritage)\b/i, 'Museums and Institutions'],
  [/\b(arts?\s*and\s*crafts?|handmade)\b/i, 'Arts and Crafts'],
  [/\b(wholesale)\b/i, 'Wholesale'],
  [/\b(arbitration|mediation|dispute resolution)\b/i, 'Alternative Dispute Resolution'],
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

type SearchPhase = 'classifying' | 'searching' | 'thinking';

const PHASE_ORDER: SearchPhase[] = ['classifying', 'searching', 'thinking'];

const PHASE_META: Record<SearchPhase, { label: string; detail: string }> = {
  classifying: { label: 'Understanding your query',  detail: 'Classifying intent with AI…'   },
  searching:   { label: 'Searching companies',        detail: 'Scanning 500k+ companies…'     },
  thinking:    { label: 'Thinking',                   detail: 'Analyzing and preparing results…' },
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
            {phase === 'thinking' ? '🧠 Thinking' : isAgentic ? '🤖 AI Agent Working' : '✨ AI Searching'}
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
  const abortRef = useRef<AbortController | null>(null);

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
    // Cancel any in-flight request so stale responses don't overwrite newer results
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    const signal = abortRef.current.signal;
    // Strip wrapping quotes if the entire string is quoted
    let cleaned = searchQuery.trim();
    if (cleaned.length >= 2 && cleaned.startsWith('"') && cleaned.endsWith('"')) {
      cleaned = cleaned.slice(1, -1);
      setQuery(cleaned);
    }
    setLoading(true);
    try {
      const apiFilters = toApiFilters(currentFilters);
      const data = await intelligentSearch(cleaned, apiFilters, page, signal);
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
      if (axios.isCancel(err) || (err instanceof DOMException && err.name === 'AbortError')) return;
      console.error('Search failed:', err);
    } finally {
      if (!signal.aborted) setLoading(false);
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
                <li>"find me companies that announced fund raising in last year in Australia"</li>
                <li>"give me more information about Infosys"</li>
              </ul>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

