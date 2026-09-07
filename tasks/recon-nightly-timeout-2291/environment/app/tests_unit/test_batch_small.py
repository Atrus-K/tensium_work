from datetime import date

from recon.config import DEFAULT_CONFIG
from recon.matching.batch import find_batch
from recon.models import Invoice


def inv(i, due, amount):
    return Invoice(id=i, customer_id=7, reference=f"RE-2026-{i:06d}", amount_cents=amount, currency="EUR",
                   due_date=due, status="open")


TOY = [
    inv(501, date(2026, 5, 2), 12000),
    inv(507, date(2026, 5, 18), 8000),
    inv(512, date(2026, 6, 1), 20000),
    inv(520, date(2026, 6, 20), 8000),
    inv(533, date(2026, 8, 14), 12000),
]


def test_two_oldest_invoices():
    run = find_batch(TOY, 20000, DEFAULT_CONFIG)
    assert [i.id for i in run] == [501, 507]


def test_tolerance_of_one_cent():
    assert [i.id for i in find_batch(TOY, 20001, DEFAULT_CONFIG)] == [501, 507]
    assert find_batch(TOY, 20002, DEFAULT_CONFIG) is None


def test_no_run_for_unpayable_amount():
    assert find_batch(TOY, 33333, DEFAULT_CONFIG) is None


def test_single_invoice_is_not_a_batch():
    assert find_batch(TOY[:1], 12000, DEFAULT_CONFIG) is None
