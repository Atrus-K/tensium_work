from datetime import date

import pytest

from recon.statements.parser import StatementError, parse_amount, parse_date, parse_statement, processing_order

HEADER = "Umsatz-ID;Buchungstag;Valutadatum;Auftraggeber;IBAN;Verwendungszweck;Betrag;Waehrung\n"


def test_german_amounts():
    assert parse_amount("1.234,56") == 123456
    assert parse_amount("-12,50") == -1250
    assert parse_amount("750") == 75000
    assert parse_amount("0,5") == 50
    assert parse_amount("12.345.678,01") == 1234567801


def test_bad_amount_raises():
    with pytest.raises(StatementError):
        parse_amount("12,345")


def test_dates():
    assert parse_date("31.08.2026") == date(2026, 8, 31)
    assert parse_date("2026-08-31") == date(2026, 8, 31)


def test_parse_file_and_processing_order(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text(
        HEADER
        + 'NW-000002;04.08.2026;04.08.2026;"Müller GmbH";DE89 3704 0044 0532 0130 00;RE-2026-000001;1.000,00;EUR\n'
        + "NW-000001;05.08.2026;05.08.2026;Schmidt KG;;Rechnung August;-4,90;EUR\n"
        + "NW-000003;03.08.2026;04.08.2026;Late Booking;;Korrektur;20,00;EUR\n",
        encoding="utf-8",
    )
    lines = parse_statement(p)
    assert [ln.line_id for ln in lines] == ["NW-000002", "NW-000001", "NW-000003"]
    assert lines[0].amount_cents == 100000 and lines[0].remitter == "Müller GmbH"
    assert lines[1].amount_cents == -490 and lines[1].iban == ""
    assert [ln.line_id for ln in processing_order(lines)] == ["NW-000003", "NW-000002", "NW-000001"]


def test_duplicate_id_rejected(tmp_path):
    p = tmp_path / "dup.csv"
    p.write_text(HEADER + "X;04.08.2026;04.08.2026;A;;p;1,00;EUR\nX;04.08.2026;04.08.2026;A;;p;1,00;EUR\n", encoding="utf-8")
    with pytest.raises(StatementError):
        parse_statement(p)
