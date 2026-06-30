from src.normalize.phone import normalize_phone
from src.normalize.dates import normalize_month, normalize_year
from src.normalize.country import normalize_country, parse_location
from src.normalize.skills import canonical_skill
from src.normalize.text import normalize_email, company_key


def test_phone_e164():
    assert normalize_phone("098765 43210", "IN") == "+919876543210"   # India default
    assert normalize_phone("+91 99001 23456") == "+919900123456"      # already has +91
    assert normalize_phone("(415) 555-2671", "US") == "+14155552671"  # US still supported
    assert normalize_phone("+44 20 7946 0958", "GB") == "+442079460958"
    assert normalize_phone("not a phone") is None      # garbage -> None, not invented
    assert normalize_phone("") is None


def test_dates():
    assert normalize_month("Jan 2021") == "2021-01"
    assert normalize_month("01/2021") == "2021-01"
    assert normalize_month("2021-01") == "2021-01"
    assert normalize_month("Present") == "present"
    assert normalize_month("garbage") is None
    assert normalize_year("Stanford, 2018") == 2018


def test_country_and_state_disambiguation():
    assert normalize_country("India") == "IN"
    assert normalize_country("United States") == "US"
    assert normalize_country("UK") == "GB"          # alias wins over literal
    # Indian state name implies India
    assert parse_location("Bengaluru, Karnataka")["country"] == "IN"
    assert parse_location("Bengaluru, Karnataka")["region"] == "Karnataka"
    assert parse_location("Mumbai, Maharashtra, India")["city"] == "Mumbai"
    # US still works and CA stays California, not Canada
    assert parse_location("San Francisco, CA")["country"] == "US"
    assert parse_location("San Francisco, CA")["region"] == "CA"
    assert parse_location("London, UK")["country"] == "GB"


def test_skill_canonicalization():
    assert canonical_skill("js") == "JavaScript"
    assert canonical_skill("postgres") == "PostgreSQL"
    assert canonical_skill("k8s") == "Kubernetes"
    assert canonical_skill("") is None


def test_email():
    assert normalize_email("Jane.Doe@Gmail.com ") == "jane.doe@gmail.com"
    assert normalize_email("not-an-email") is None


def test_company_key_matches_variants():
    assert company_key("Google") == company_key("Google LLC")
    assert company_key("Acme Ltd") == company_key("Acme")
