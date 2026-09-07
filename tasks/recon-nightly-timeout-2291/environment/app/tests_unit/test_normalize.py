from recon.matching.normalize import extract_reference_tokens, normalize_iban, normalize_reference


def test_examples_from_spec_table():
    assert normalize_reference("RE-2026-004471") == "RE20264471"
    assert normalize_reference("re 2026/004471") == "RE20264471"
    assert normalize_reference("RE-2026-4471") == "RE20264471"
    assert normalize_reference("RE-2026004471") == "RE2026004471"
    assert normalize_reference("Müller & Söhne GmbH") == "MUELLERSOEHNEGMBH"
    assert normalize_reference("Bau 0000 Nord") == "BAU0NORD"


def test_umlauts_and_sharp_s_both_cases():
    assert normalize_reference("ÄÖÜ äöü ß") == "AEOEUEAEOEUESS"
    assert normalize_reference("Straße") == "STRASSE"


def test_tokens_in_purpose_text():
    assert extract_reference_tokens("Zahlung RE-2026-004471 Danke") == ["RE20264471"]
    assert extract_reference_tokens("RE 2026 004471, RE 2026 004472") == ["RE20264471", "RE20264472"]
    assert extract_reference_tokens("Rechnung August") == []
    assert extract_reference_tokens("KD-01188 RE-2026-004471") == ["KD1188", "RE20264471"]


def test_tokens_are_distinct_and_boundary_aware():
    assert extract_reference_tokens("RE-2026-004471 re/2026/4471") == ["RE20264471"]
    # glued to a preceding word or followed by digits: not a token
    assert extract_reference_tokens("RechnungRE-2026-004471") == []
    assert extract_reference_tokens("vom 12.08.2026") == []


def test_iban_whitespace_and_case():
    assert normalize_iban("de89 3704 0044 0532 0130 00") == "DE89370400440532013000"
