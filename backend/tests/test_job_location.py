"""services.job_location: location strings -> ISO country codes (shared by jobs + contracts)."""
import pytest

from services.job_location import (
    from_country_codes, is_us_location, job_countries, normalize_country, to_country_codes,
)

CASES = [
    # United States
    ("Austin, TX", ["US"]),
    ("San Francisco, CA", ["US"]),
    ("New York, NY", ["US"]),
    ("New York City", ["US"]),
    ("Seattle, Washington", ["US"]),
    ("Washington, DC", ["US"]),
    ("Atlanta, Georgia", ["US"]),
    ("Albuquerque, New Mexico", ["US"]),
    ("Remote - US", ["US"]),
    ("US Remote", ["US"]),
    ("Remote (US)", ["US"]),
    ("Remote in the US", ["US"]),
    ("United States", ["US"]),
    ("USA", ["US"]),
    ("U.S.", ["US"]),
    ("US-CA-San Jose", ["US"]),
    ("USA - Texas", ["US"]),
    ("Chicago, IL (Hybrid)", ["US"]),
    ("Boston or Remote", ["US"]),
    ("Hoboken, NJ", ["US"]),
    ("Vancouver, WA", ["US"]),
    ("Portland, OR", ["US"]),
    ("Richmond, VA", ["US"]),
    ("Join us in NYC", ["US"]),
    ("San Juan, Puerto Rico", ["US"]),
    # Canada
    ("Toronto, ON", ["CA"]),
    ("Toronto, Canada", ["CA"]),
    ("Toronto, CA", ["CA"]),
    ("Vancouver, BC", ["CA"]),
    ("Vancouver", ["CA"]),
    ("Montréal, Québec", ["CA"]),
    ("Remote - Canada", ["CA"]),
    ("Calgary, Alberta", ["CA"]),
    # United Kingdom / Ireland
    ("London, UK", ["GB"]),
    ("London, United Kingdom", ["GB"]),
    ("London", ["GB"]),
    ("Edinburgh, Scotland", ["GB"]),
    ("Remote - UK", ["GB"]),
    ("Dublin, Ireland", ["IE"]),
    ("Dublin", ["IE"]),
    ("Cork", ["IE"]),
    # Europe
    ("Berlin, Germany", ["DE"]),
    ("Berlin", ["DE"]),
    ("Munich", ["DE"]),
    ("Paris, France", ["FR"]),
    ("Paris", ["FR"]),
    ("Amsterdam, Netherlands", ["NL"]),
    ("Warsaw, Poland", ["PL"]),
    ("Barcelona", ["ES"]),
    ("Zürich", ["CH"]),
    ("Lisbon, Portugal", ["PT"]),
    ("Stockholm", ["SE"]),
    # India / APAC / LATAM / MEA
    ("Bangalore", ["IN"]),
    ("Bengaluru, Karnataka, India", ["IN"]),
    ("Hyderabad, Telangana", ["IN"]),
    ("Chennai, TN, India", ["IN"]),
    ("Gurugram", ["IN"]),
    ("Singapore", ["SG"]),
    ("Tokyo, Japan", ["JP"]),
    ("Sydney, NSW", ["AU"]),
    ("Melbourne, Australia", ["AU"]),
    ("Auckland, New Zealand", ["NZ"]),
    ("Mexico City", ["MX"]),
    ("São Paulo, Brazil", ["BR"]),
    ("Buenos Aires", ["AR"]),
    ("Bogotá, Colombia", ["CO"]),
    ("Tel Aviv, Israel", ["IL"]),
    ("Dubai, UAE", ["AE"]),
    ("Tbilisi, Georgia", ["GE"]),
    ("Manila, Philippines", ["PH"]),
    # Ambiguous cities resolved by adjacent tokens
    ("Dublin, CA", ["US"]),
    ("Dublin, OH", ["US"]),
    ("London, ON", ["CA"]),
    ("London, Ontario", ["CA"]),
    ("Paris, TX", ["US"]),
    ("Cambridge, MA", ["US"]),
    ("Cambridge", ["GB"]),
    ("Cambridge, England", ["GB"]),
    ("Birmingham, AL", ["US"]),
    ("Manchester, NH", ["US"]),
    ("Athens, GA", ["US"]),
    ("Perth, Australia", ["AU"]),
    ("Waterloo, Ontario", ["CA"]),
    # Multi-location
    ("New York, NY; London, UK", ["GB", "US"]),
    ("Remote, Canada; Remote, United Kingdom; Remote, US", ["CA", "GB", "US"]),
    ("San Francisco | Toronto | Bangalore", ["CA", "IN", "US"]),
    ("Austin, TX / Dublin, Ireland", ["IE", "US"]),
    # Unknown
    ("Remote", []),
    ("Anywhere", []),
    ("Worldwide", []),
    ("Multiple Locations", []),
    ("Hybrid", []),
    ("", []),
    (None, []),
    ("-", []),
    ("3 Locations", []),
]


@pytest.mark.parametrize("location, expected", CASES)
def test_job_countries(location, expected):
    assert job_countries(location) == expected


def test_case_count():
    assert len(CASES) >= 80


def test_new_mexico_and_new_england_are_not_countries():
    assert job_countries("Santa Fe, New Mexico") == ["US"]
    assert job_countries("Boston, New England") == ["US"]


def test_regions_expand_to_members():
    emea = job_countries("Remote - EMEA")
    assert "GB" in emea and "DE" in emea and "US" not in emea
    assert "US" not in job_countries("APAC") and "IN" in job_countries("APAC")
    assert set(job_countries("Remote - North America")) == {"US", "CA"}
    assert "BR" in job_countries("LATAM")


@pytest.mark.parametrize("location, title, expected", [
    ("Remote", "Software Engineer (US)", ["US"]),
    ("Remote", "Account Executive - UK", ["GB"]),
    ("", "Solutions Engineer, EMEA", "EMEA"),
    ("Remote", "Engineer", []),
    ("Austin, TX", "Account Executive - UK", ["US"]),  # a known location wins over the title
])
def test_title_hints_only_when_location_unknown(location, title, expected):
    got = job_countries(location, title)
    if expected == "EMEA":
        assert "GB" in got and "US" not in got
    else:
        assert got == expected


@pytest.mark.parametrize("location, expected", [
    ("Austin, TX", True), ("Remote - US", True), ("London, UK; New York, NY", True),
    ("Toronto, ON", False), ("Bangalore", False), ("Remote", None), ("", None),
])
def test_is_us_location(location, expected):
    assert is_us_location(location) == expected


@pytest.mark.parametrize("value, expected", [
    ("US", "US"), ("us", "US"), ("USA", "US"), ("United States", "US"), ("united states of america", "US"),
    ("U.S.", "US"), ("UK", "GB"), ("United Kingdom", "GB"), ("GB", "GB"), ("India", "IN"), ("IN", "IN"),
    ("Canada", "CA"), ("Germany", "DE"), ("", None), (None, None), ("Narnia", None), ("ZZ", None),
])
def test_normalize_country(value, expected):
    assert normalize_country(value) == expected


def test_country_codes_round_trip():
    assert to_country_codes(["US", "GB", "US"]) == ",GB,US,"
    assert to_country_codes([]) is None
    assert from_country_codes(",GB,US,") == ["GB", "US"]
    assert from_country_codes(None) == []
