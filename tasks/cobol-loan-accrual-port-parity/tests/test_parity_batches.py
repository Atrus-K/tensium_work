"""Byte-level parity of the port against the mainframe output on two full batches."""
from __future__ import annotations

import hashlib
from pathlib import Path

from conftest import APP_DIR, FIXTURES, field_diffs, run_cli

# The workspace's reference data is the parity target and must not be edited to make
# the numbers line up (ticket LND-4127 acceptance criterion).
DATA_SHA256 = {
    "HOLIDAYS.dat": "fb5dbf050605247a7bc30259d21771916fd9776593bb1c51494afdea75444b1f",
    "LNMAST_202403.dat": "1badaaaa0283aeb3db2d9ba9d9ee18d998d5b91c5bc9ebcc9676e3d2c1bdf996",
    "LNTRAN_202403.dat": "8d05023ebb79154058f4af5827ecd388abab1d42d6cdd279c0b30743d4f56b8e",
    "MAINFRAME_LNOUT_202403.dat": "77e629fdd6c943954c9ed5e4ca2d1116425363fdcfd4f08057779fd0913891ae",
    "RATETBL_202403.dat": "d95519e4f92564aa64dfe9da8fa43afd68034221829487498e4101e29298b791",
}


def _report(diffs: list[str], limit: int = 40) -> str:
    head = "\n".join(diffs[:limit])
    more = f"\n... {len(diffs) - limit} more" if len(diffs) > limit else ""
    return f"{len(diffs)} field difference(s) against the mainframe output:\n{head}{more}"


def test_reference_data_untouched():
    for name, digest in DATA_SHA256.items():
        actual = hashlib.sha256((APP_DIR / "data" / name).read_bytes()).hexdigest()
        assert actual == digest, f"data/{name} was modified; the reference batch data is read-only"


def test_march_batch_field_parity(march_output, march_expected):
    assert len(march_output.details) == len(march_expected.details) == 394
    diffs = field_diffs(march_expected, march_output)
    assert not diffs, _report(diffs)


def test_march_batch_byte_identical(march_output, march_expected):
    assert march_output.raw == march_expected.raw


def test_march_recon_reports_match(tmp_path: Path, march_output):
    out = tmp_path / "LNOUT.dat"
    out.write_bytes(march_output.raw)
    proc = run_cli("recon", "--legacy", str(APP_DIR / "data" / "MAINFRAME_LNOUT_202403.dat"),
                   "--candidate", str(out), check=False)
    assert proc.returncode == 0, proc.stdout[-3000:]
    assert "RESULT: MATCH" in proc.stdout
    assert "records_mismatched=0" in proc.stdout and "field_mismatches=0" in proc.stdout


def test_recon_still_detects_a_difference(tmp_path: Path, march_expected):
    """The recon tool must not have been neutered: a single flipped sign must be reported."""
    corrupted = bytearray(march_expected.raw)
    # LO-BALANCE ends at offset 31 of the first record: flip its overpunch to the negative zone
    ch = chr(corrupted[31])
    corrupted[31] = ord("}JKLMNOPQR"["{ABCDEFGHI".index(ch)]) if ch in "{ABCDEFGHI" else ord("{")
    bad = tmp_path / "bad.dat"
    bad.write_bytes(bytes(corrupted))
    proc = run_cli("recon", "--legacy", str(APP_DIR / "data" / "MAINFRAME_LNOUT_202403.dat"),
                   "--candidate", str(bad), check=False)
    assert proc.returncode != 0
    assert "RESULT: MISMATCH" in proc.stdout
    assert "BALANCE" in proc.stdout


def test_may_batch_field_parity(may_output, may_expected):
    """A different batch: 300 accounts, 6-tier table, as-of 2024-05-31, and a state banking
    holiday (2024-05-15) that is not in the March calendar and that several due dates roll across."""
    assert len(may_output.details) == len(may_expected.details) == 295
    diffs = field_diffs(may_expected, may_output)
    assert not diffs, _report(diffs)


def test_may_batch_byte_identical(may_output, may_expected):
    assert may_output.raw == may_expected.raw


def test_may_recon_reports_match(tmp_path: Path, may_output):
    out = tmp_path / "LNOUT.dat"
    out.write_bytes(may_output.raw)
    proc = run_cli("recon", "--legacy", str(FIXTURES / "batch_202405" / "MAINFRAME_LNOUT_202405.dat"),
                   "--candidate", str(out), check=False)
    assert proc.returncode == 0, proc.stdout[-3000:]
    assert "RESULT: MATCH" in proc.stdout
