"""
Job location -> countries (shared by the full-time and contracts pipelines;
neither imports the other for this).

    job_countries(location, title=None) -> sorted unique ISO-3166 alpha-2 codes
    ([] = unknown: "Remote", "Anywhere", "Multiple Locations", "")

Multi-location strings are split on ; | • / newlines ("Remote, Canada; Remote,
United Kingdom; Remote, US" -> [CA, GB, US]). Ambiguous city names (Dublin,
London, Paris, Cambridge, ...) follow an adjacent state/province/country token
("Dublin, CA" -> US, "London, ON" -> CA) and default to their best-known
country otherwise. Region words in the title ("- UK", "(EMEA)") are used only
when the location itself is unknown or a bare "Remote".

Stored as a delimited string column country_codes (",US,GB,") so one LIKE
works on SQLite and PostgreSQL: see to_country_codes() / country_filter().
normalize_country() maps profile values ("United States", "USA") to ISO-2.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

I = re.IGNORECASE

# ----------------------------------------------------------------- reference data

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC", "washington dc": "DC",
    "washington d.c.": "DC", "puerto rico": "PR",
}
US_STATE_CODES = set(US_STATES.values())
CA_PROVINCES = {
    "ontario": "ON", "british columbia": "BC", "quebec": "QC", "québec": "QC", "alberta": "AB",
    "manitoba": "MB", "nova scotia": "NS", "new brunswick": "NB", "saskatchewan": "SK",
    "newfoundland": "NL", "prince edward island": "PE", "yukon": "YT",
}
CA_PROVINCE_CODES = set(CA_PROVINCES.values()) | {"NT", "NU"}
IN_STATES = {"karnataka", "maharashtra", "telangana", "tamil nadu", "haryana", "uttar pradesh", "kerala",
             "gujarat", "west bengal", "andhra pradesh", "rajasthan"}

COUNTRY_NAMES = {
    "US": ["united states of america", "united states", "usa", "u.s.a.", "u.s.a", "u.s.", "us", "america"],
    "CA": ["canada"],
    "GB": ["united kingdom", "uk", "u.k.", "great britain", "britain", "england", "scotland", "wales",
           "northern ireland", "gbr"],
    "IE": ["ireland", "republic of ireland"],
    "DE": ["germany", "deutschland"], "FR": ["france"], "ES": ["spain", "españa"], "IT": ["italy", "italia"],
    "NL": ["netherlands", "the netherlands", "holland"], "BE": ["belgium"], "LU": ["luxembourg"],
    "CH": ["switzerland"], "AT": ["austria"], "SE": ["sweden"], "NO": ["norway"], "DK": ["denmark"],
    "FI": ["finland"], "IS": ["iceland"], "PT": ["portugal"], "PL": ["poland"], "CZ": ["czech republic", "czechia"],
    "SK": ["slovakia"], "HU": ["hungary"], "RO": ["romania"], "BG": ["bulgaria"], "GR": ["greece"],
    "HR": ["croatia"], "SI": ["slovenia"], "RS": ["serbia"], "EE": ["estonia"], "LV": ["latvia"],
    "LT": ["lithuania"], "UA": ["ukraine"], "CY": ["cyprus"], "MT": ["malta"], "TR": ["turkey", "türkiye"],
    "IL": ["israel"], "AE": ["united arab emirates", "uae"], "SA": ["saudi arabia"], "QA": ["qatar"],
    "EG": ["egypt"], "NG": ["nigeria"], "KE": ["kenya"], "ZA": ["south africa"], "MA": ["morocco"],
    "TN": ["tunisia"], "MU": ["mauritius"],
    "IN": ["india"], "PK": ["pakistan"], "BD": ["bangladesh"], "LK": ["sri lanka"],
    "CN": ["china", "mainland china", "prc"], "HK": ["hong kong"], "TW": ["taiwan"], "JP": ["japan"],
    "KR": ["south korea", "korea", "republic of korea"], "SG": ["singapore"], "MY": ["malaysia"],
    "TH": ["thailand"], "VN": ["vietnam", "viet nam"], "ID": ["indonesia"], "PH": ["philippines"],
    "AU": ["australia"], "NZ": ["new zealand"],
    "MX": ["mexico", "méxico"], "BR": ["brazil", "brasil"], "AR": ["argentina"], "CO": ["colombia"],
    "CL": ["chile"], "PE": ["peru", "perú"], "UY": ["uruguay"], "CR": ["costa rica"], "EC": ["ecuador"],
    "GT": ["guatemala"], "DO": ["dominican republic"], "PA": ["panama"], "VE": ["venezuela"],
}

CITIES = {
    "US": ["new york city", "nyc", "manhattan", "brooklyn", "san francisco", "sf bay area", "bay area",
           "silicon valley", "seattle", "austin", "boston", "los angeles", "chicago", "denver", "atlanta",
           "miami", "phoenix", "dallas", "houston", "san diego", "san jose", "palo alto", "mountain view",
           "menlo park", "cupertino", "redwood city", "sunnyvale", "santa clara", "oakland", "berkeley",
           "irvine", "pasadena", "santa monica", "las vegas", "salt lake city", "minneapolis", "detroit",
           "pittsburgh", "philadelphia", "baltimore", "raleigh", "durham", "charlotte", "nashville",
           "columbus", "indianapolis", "milwaukee", "kansas city", "st. louis", "st louis", "tampa",
           "orlando", "jacksonville", "bellevue", "redmond", "kirkland", "boulder", "ann arbor", "san mateo",
           "foster city", "south san francisco", "sacramento", "san antonio", "plano", "reston", "mclean",
           "herndon", "jersey city", "hoboken", "cincinnati", "cleveland", "fort worth", "scottsdale",
           "tempe", "chandler", "alpharetta", "arlington", "washington dc", "new orleans", "honolulu",
           "anchorage", "omaha", "albuquerque", "tucson", "el paso", "louisville", "memphis", "richmond",
           "boise", "des moines", "madison", "provo", "lehi", "stamford", "hartford", "providence"],
    "CA": ["toronto", "montreal", "montréal", "ottawa", "calgary", "edmonton", "winnipeg", "mississauga",
           "kitchener", "quebec city", "halifax", "victoria bc", "burnaby", "markham", "gatineau"],
    "GB": ["edinburgh", "glasgow", "leeds", "liverpool", "belfast", "sheffield", "nottingham", "reading",
           "newcastle", "brighton", "cardiff", "milton keynes", "leicester", "southampton", "slough", "woking",
           "abingdon", "covent garden", "guildford", "swindon", "basingstoke"],
    "IE": ["cork", "galway", "limerick"],
    "DE": ["berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln", "stuttgart", "düsseldorf", "kleinmachnow",
           "dusseldorf", "leipzig", "dresden", "nuremberg", "karlsruhe", "bonn", "hannover", "essen",
           "dortmund", "bremen", "mannheim", "heidelberg", "darmstadt", "aachen", "potsdam", "wiesbaden"],
    "FR": ["lyon", "marseille", "toulouse", "nice", "nantes", "bordeaux", "lille", "grenoble"],
    "ES": ["madrid", "barcelona", "valencia", "seville", "sevilla", "malaga", "málaga", "bilbao"],
    "IT": ["milan", "milano", "turin", "torino", "bologna", "florence", "naples"],
    "NL": ["amsterdam", "rotterdam", "the hague", "utrecht", "eindhoven", "delft"],
    "BE": ["brussels", "antwerp", "ghent"], "CH": ["zurich", "zürich", "geneva", "lausanne", "basel", "bern"],
    "AT": ["vienna", "wien", "graz"], "SE": ["stockholm", "gothenburg", "malmö", "malmo"],
    "NO": ["oslo", "bergen"], "DK": ["copenhagen", "aarhus"], "FI": ["helsinki", "espoo", "tampere"],
    "PT": ["lisbon", "lisboa", "porto", "braga", "aveiro", "coimbra"], "PL": ["warsaw", "krakow", "kraków", "wroclaw", "wrocław", "gdansk",
                                                "gdańsk", "poznan", "poznań", "lodz", "warszawa", "katowice"],
    "CZ": ["prague", "brno"], "HU": ["budapest"], "RO": ["bucharest", "cluj-napoca", "cluj", "iasi", "timișoara", "timisoara", "brașov", "brasov"],
    "BG": ["sofia"], "GR": ["athens greece"], "EE": ["tallinn"], "LV": ["riga"], "LT": ["vilnius"],
    "UA": ["kyiv", "kiev", "lviv", "kharkiv"], "RS": ["belgrade", "novi sad"], "HR": ["zagreb"],
    "IL": ["tel aviv", "jerusalem", "haifa", "herzliya", "rehovot", "petah tikva", "ra'anana", "yokneam"], "AE": ["dubai", "abu dhabi"], "TR": ["istanbul", "ankara"],
    "IN": ["bangalore", "bengaluru", "mumbai", "hyderabad", "chennai", "pune", "delhi", "new delhi", "gurgaon",
           "gurugram", "noida", "kolkata", "ahmedabad", "jaipur", "kochi", "thiruvananthapuram", "coimbatore",
           "chandigarh", "indore", "mysore", "mysuru", "vadodara", "visakhapatnam", "mohali", "sanand",
           "telengana", "bhubaneswar", "nagpur", "trivandrum"],
    "PK": ["karachi", "lahore", "islamabad"], "CN": ["beijing", "shanghai", "shenzhen", "guangzhou", "hangzhou",
                                                     "chengdu", "suzhou", "wuxi", "changzhou", "chongqing",
                                                     "changsha", "nanchang", "nanjing", "wuhan", "xi'an", "tianjin",
                                                     "dalian", "jiangsu", "jiangxi", "zhejiang", "guangdong"],
    "SA": ["riyadh", "jeddah", "dammam", "khobar"], "JP": ["tokyo", "osaka", "kyoto", "yokohama", "hiroshima", "nagoya", "fukuoka"], "KR": ["seoul", "busan", "sejong", "incheon", "daejeon", "suwon"], "TW": ["taipei", "hsinchu"],
    "PH": ["manila", "makati", "cebu", "taguig", "quezon city", "pasig"],
    "VN": ["ho chi minh city", "ho chi minh", "hồ chí minh", "hanoi", "hà nội", "ha noi", "da nang"],
    "TH": ["bangkok", "rayong", "chonburi", "chon buri"],
    "MY": ["kuala lumpur", "petaling jaya", "bayan lepas", "batu kawan", "penang", "pulau pinang", "selangor",
           "cyberjaya", "kulim"], "ID": ["jakarta"], "AU": ["sydney", "melbourne australia", "brisbane", "adelaide",
                                                      "canberra", "new south wales", "nsw", "queensland", "qld", "tasmania"],
    "NZ": ["auckland", "wellington"], "MX": ["mexico city", "guadalajara", "monterrey", "cdmx", "aguascalientes",
                                             "queretaro", "querétaro", "tijuana"],
    "BR": ["são paulo", "sao paulo", "rio de janeiro", "belo horizonte", "florianópolis", "florianopolis",
           "curitiba", "porto alegre", "campinas", "barueri", "são bernardo do campo", "recife"],
    "AR": ["buenos aires", "córdoba argentina"], "CO": ["bogota", "bogotá", "medellin", "medellín"],
    "CL": ["santiago de chile"], "PE": ["lima peru"], "UY": ["montevideo"], "CR": ["san josé costa rica"],
    "ZA": ["cape town", "johannesburg", "midrand", "pretoria", "durban"], "NG": ["lagos"], "KE": ["nairobi"], "EG": ["cairo", "giza"],
    "MA": ["casablanca", "rabat"], "TN": ["tunis", "ariana"], "MU": ["ebene"],
}

# Same name in several countries: resolved by an adjacent state/province/country token.
AMBIGUOUS_CITIES = {
    "london": "GB", "manchester": "GB", "birmingham": "GB", "cambridge": "GB", "oxford": "GB", "bristol": "GB",
    "dublin": "IE", "paris": "FR", "rome": "IT", "athens": "GR", "vancouver": "CA", "waterloo": "CA",
    "melbourne": "AU", "perth": "AU", "victoria": "CA", "hamilton": "CA", "richmond": "US", "portland": "US",
    "santiago": "CL", "cordoba": "AR", "córdoba": "AR", "valencia": "ES", "lima": "PE", "san josé": "CR",
    "georgia": "US", "roma": "IT", "hanover": "DE",
}

REGIONS = {
    "EMEA": ["emea", "europe, middle east and africa", "europe, middle east & africa"],
    "EUROPE": ["europe", "eu", "european union", "eea", "dach", "nordics", "benelux", "cee"],
    "APAC": ["apac", "apj", "asia pacific", "asia-pacific", "anz", "asia"],
    "LATAM": ["latam", "latin america", "south america", "central america"],
    "AMER": ["amer", "americas", "the americas"],
    "NA": ["north america", "noram", "us & canada", "us and canada", "usa & canada", "usa and canada"],
}
_EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT",
       "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}
REGION_MEMBERS = {
    "EUROPE": _EU | {"GB", "CH", "NO", "IS", "RS", "UA", "TR"},
    "EMEA": _EU | {"GB", "CH", "NO", "IS", "RS", "UA", "TR", "IL", "AE", "SA", "QA", "EG", "NG", "KE", "ZA", "MA"},
    "APAC": {"IN", "PK", "BD", "LK", "CN", "HK", "TW", "JP", "KR", "SG", "MY", "TH", "VN", "ID", "PH", "AU", "NZ"},
    "LATAM": {"MX", "BR", "AR", "CO", "CL", "PE", "UY", "CR", "EC", "GT", "DO", "PA", "VE"},
    "AMER": {"US", "CA", "MX", "BR", "AR", "CO", "CL", "PE", "UY", "CR", "EC", "GT", "DO", "PA", "VE"},
    "NA": {"US", "CA"},
}

# ----------------------------------------------------------------- regexes


def _key(word: str) -> str:
    """Lookup key for a regex match: "İstanbul".lower() is "i̇stanbul" (i + U+0307), which no table holds."""
    return word.lower().replace("\u0307", "")


def _rx(words: Iterable[str]) -> re.Pattern:
    words = sorted(set(words), key=len, reverse=True)
    return re.compile(r"(?<![\w])(" + "|".join(re.escape(w) for w in words) + r")(?![\w])", I)


_COUNTRY_LOOKUP = {alias: code for code, aliases in COUNTRY_NAMES.items() for alias in aliases}
_COUNTRY_RX = _rx([a for a in _COUNTRY_LOOKUP if a not in ("us", "america")])
_US_TOKEN_RX = re.compile(r"(?<![\w])(US|U\.S\.?|Usa)(?![\w])")  # "us" lowercase is the pronoun
_CITY_LOOKUP = {city: code for code, cities in CITIES.items() for city in cities}
_CITY_RX = _rx(_CITY_LOOKUP)
_AMBIG_RX = _rx(AMBIGUOUS_CITIES)
_US_STATE_RX = _rx([s for s in US_STATES if s not in ("georgia", "washington")])
_CA_PROV_RX = _rx(CA_PROVINCES)
_IN_STATE_RX = _rx(IN_STATES)
_REGION_LOOKUP = {alias: code for code, aliases in REGIONS.items() for alias in aliases}
_REGION_RX = _rx(_REGION_LOOKUP)
_CODE_RX = re.compile(r"(?:,|\s-|\(|\s)\s*([A-Z]{2})(?![A-Za-z])")
# "Heredia, CR", "QUEZON CITY, PH": a trailing ISO-2 that is no US state / CA province code
_TRAILING_ISO2_RX = re.compile(r",\s*([A-Z]{2})\s*$")
# ISO-3 codes in upper case: "MYS - PETALING JAYA", "Rehovot,ISR", "KOR-Gyeonggi-do". Codes that are
# also English words (CAN, ARE, PER, COL) are left out.
ISO3 = {
    "USA": "US", "GBR": "GB", "IRL": "IE", "DEU": "DE", "FRA": "FR", "ESP": "ES", "ITA": "IT", "NLD": "NL",
    "BEL": "BE", "LUX": "LU", "CHE": "CH", "AUT": "AT", "SWE": "SE", "NOR": "NO", "DNK": "DK", "FIN": "FI",
    "ISL": "IS", "PRT": "PT", "POL": "PL", "CZE": "CZ", "SVK": "SK", "HUN": "HU", "ROU": "RO", "BGR": "BG",
    "GRC": "GR", "HRV": "HR", "SVN": "SI", "SRB": "RS", "EST": "EE", "LVA": "LV", "LTU": "LT", "UKR": "UA",
    "CYP": "CY", "MLT": "MT", "TUR": "TR", "ISR": "IL", "SAU": "SA", "QAT": "QA", "EGY": "EG", "NGA": "NG",
    "KEN": "KE", "ZAF": "ZA", "MAR": "MA", "TUN": "TN", "MUS": "MU", "IND": "IN", "PAK": "PK", "BGD": "BD",
    "LKA": "LK", "CHN": "CN", "HKG": "HK", "TWN": "TW", "JPN": "JP", "KOR": "KR", "SGP": "SG", "MYS": "MY",
    "THA": "TH", "VNM": "VN", "IDN": "ID", "PHL": "PH", "AUS": "AU", "NZL": "NZ", "MEX": "MX", "BRA": "BR",
    "ARG": "AR", "CHL": "CL", "URY": "UY", "CRI": "CR", "ECU": "EC", "GTM": "GT", "DOM": "DO", "PAN": "PA",
}
_ISO3_RX = re.compile(r"(?<![A-Za-z])(" + "|".join(ISO3) + r")(?![A-Za-z])")
_SPLIT_RX = re.compile(r"\s*(?:;|\||•|\n|\s/\s|\s+or\s+)\s*", I)

# "Georgia" is a US state far more often than the country in US job boards;
# "Washington" is the state/DC. Both handled explicitly.
_GEORGIA_COUNTRY_RX = re.compile(r"\b(tbilisi|georgia \(country\)|republic of georgia)\b", I)


def _segment_countries(seg: str) -> tuple[set, Optional[str]]:
    """Countries named by one location segment, plus a region code if only a region is named."""
    found: set = set()
    s = seg.strip()
    if not s:
        return found, None
    for m in _COUNTRY_RX.finditer(s):
        if re.search(r"\bnew\s+$", s[max(0, m.start() - 4):m.start()], I):
            continue  # New Mexico, New England
        found.add(_COUNTRY_LOOKUP[_key(m.group(1))])
    if _US_TOKEN_RX.search(s):
        found.add("US")
    has_foreign_country = bool(found - {"US"})
    for m in _CITY_RX.finditer(s):
        found.add(_CITY_LOOKUP[_key(m.group(1))])
    if _US_STATE_RX.search(s):
        found.add("US")
    if re.search(r"(?<![\w])washington(?![\w])", s, I) and not has_foreign_country:
        found.add("US")
    if re.search(r"(?<![\w])georgia(?![\w])", s, I):
        found.add("GE" if _GEORGIA_COUNTRY_RX.search(s) else "US")
    if _CA_PROV_RX.search(s):
        found.add("CA")
    if _IN_STATE_RX.search(s):
        found.add("IN")
    # Two-letter codes: "Austin, TX", "Toronto, ON", "Remote - US". A code next to a
    # named foreign country ("Chennai, TN, India") is that country's state, not US.
    codes = [m.group(1) for m in _CODE_RX.finditer(s)]
    city_country = {_CITY_LOOKUP[_key(m.group(1))] for m in _CITY_RX.finditer(s)}
    for code in codes:
        if code in ("US",):
            found.add("US")
        elif code == "CA":
            # California, unless the city is Canadian ("Toronto, CA")
            found.add("CA" if "CA" in city_country and "US" not in city_country else "US")
        elif code in US_STATE_CODES and not has_foreign_country and not (city_country - {"US"}):
            found.add("US")
        elif code in CA_PROVINCE_CODES and code not in US_STATE_CODES and not has_foreign_country:
            found.add("CA")
        elif code == "UK" or code == "GB":
            found.add("GB")
    m = _TRAILING_ISO2_RX.search(s)
    if m and not found and m.group(1) in COUNTRY_NAMES and m.group(1) not in US_STATE_CODES | CA_PROVINCE_CODES:
        found.add(m.group(1))
    for m in _ISO3_RX.finditer(s):
        found.add(ISO3[m.group(1)])
    # Ambiguous cities only when nothing else in the segment says where they are.
    for m in _AMBIG_RX.finditer(s):
        name = _key(m.group(1))
        if name == "georgia":
            continue
        if not found:
            found.add(AMBIGUOUS_CITIES[name])
    region = None
    if not found:
        m = _REGION_RX.search(s)
        if m:
            region = _REGION_LOOKUP[_key(m.group(1))]
    return found, region


_TITLE_HINT_RX = re.compile(
    r"(?<![\w])(US|USA|U\.S\.|United States|UK|U\.K\.|United Kingdom|EMEA|APAC|APJ|LATAM|AMER|Americas|"
    r"North America|Europe|EU|Canada|India|Germany|France|Ireland|Netherlands|Spain|Poland|Australia|Japan|"
    r"Singapore|Brazil|Mexico|Israel|London|Dublin|Berlin|Amsterdam|Toronto|Bangalore|Bengaluru)(?![\w])")


def _title_hint(title: str) -> tuple[set, Optional[str]]:
    countries: set = set()
    region = None
    for m in _TITLE_HINT_RX.finditer(title or ""):
        c, r = _segment_countries(m.group(1))
        if not c and not r:
            c, r = _segment_countries(m.group(1).lower())
        countries |= c
        region = region or r
    return countries, (None if countries else region)


def job_countries(location: Optional[str], title: Optional[str] = None) -> list[str]:
    """
    ISO-2 codes a job location names, sorted unique. [] = unknown / worldwide
    ("Remote", "Anywhere", "Multiple Locations", ""). A region ("EMEA",
    "Remote - APAC") expands to its member countries. Region words in the title
    are used only when the location names no country.
    """
    raw = str(location or "").strip()
    countries: set = set()
    regions: list = []
    for seg in _SPLIT_RX.split(raw) if raw else []:
        c, r = _segment_countries(seg)
        countries |= c
        if r:
            regions.append(r)
    if not countries and not regions and title:
        tc, tr = _title_hint(title)
        countries |= tc
        if tr:
            regions.append(tr)
    if not countries:
        for r in regions:
            countries |= REGION_MEMBERS.get(r, set())
    return sorted(countries)


def is_us_location(location: Optional[str], title: Optional[str] = None) -> Optional[bool]:
    """True = a US location (incl. US-remote); False = only elsewhere; None = unknown."""
    codes = job_countries(location, title)
    if not codes:
        return None
    return "US" in codes


# ----------------------------------------------------------------- storage + query

def to_country_codes(countries: Optional[Iterable[str]]) -> Optional[str]:
    """['CA','US'] -> ',CA,US,' (None when unknown). Fits String(200)."""
    codes = sorted({c.upper() for c in countries or [] if c})
    if not codes:
        return None
    text = "," + ",".join(codes) + ","
    return text if len(text) <= 200 else None  # "everywhere" is as good as unknown


def from_country_codes(value: Optional[str]) -> list[str]:
    return [c for c in (value or "").split(",") if c]


_NAME_TO_ISO = dict(_COUNTRY_LOOKUP)
_NAME_TO_ISO.update({"america": "US", "us": "US", "gb": "GB", "united states": "US",
                     "united states of america": "US", "u.s.": "US", "u.s": "US"})


def normalize_country(value: Optional[str]) -> Optional[str]:
    """User-profile / query value ('US', 'us', 'United States', 'USA', 'India', 'UK') -> ISO-2, else None."""
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    if len(v) == 2 and v.isalpha():
        v2 = v.upper()
        if v2 == "UK":
            return "GB"
        return v2 if v2 in COUNTRY_NAMES or v2 == "GE" else None
    return _NAME_TO_ISO.get(v.lower().rstrip("."))


def country_filter(country_codes_col, country: str, confirmed_only: bool = False):
    """
    SQL condition: visible to a viewer in ``country``. Unknown-location jobs
    (NULL/'') are visible to everyone unless ``confirmed_only``.
    """
    from sqlalchemy import or_

    match = country_codes_col.like(f"%,{country},%")
    if confirmed_only:
        return match
    return or_(match, country_codes_col.is_(None), country_codes_col == "")
