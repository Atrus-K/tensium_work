"""Record layouts mirroring the LNACCR01 copybooks (legacy/copybooks/*.cpy).

Field order and PICTURE clauses must match the copybooks exactly: offsets are derived
from them.  Terminators reflect how the datasets arrive from the MFT job
(docs/file-transfer-notes.md): LNMAST carries packed fields and is transferred as
raw 120-byte blocks; the all-DISPLAY files get a LF after every record.
"""
from __future__ import annotations

from .copybook import Layout

# LNMAST.cpy -- loan master, copybook v3 (2019-06).  120 bytes, no terminator.
LNMAST = Layout(
    "LNMAST",
    [
        ("LM-ACCT-NO", "9(10)"),
        ("LM-CUST-NAME", "X(30)"),
        ("LM-PRODUCT-CD", "X"),
        ("LM-STATUS", "X"),
        ("LM-ORIG-DATE", "9(6)"),
        ("LM-DUE-DATE", "9(6)"),
        ("LM-LAST-ACCR-DATE", "9(6)"),
        ("LM-PRIN-BAL", "S9(11)V99"),
        ("LM-PMT-DUE-AMT", "9(9)V99", "COMP-3"),
        ("LM-GRACE-DAYS", "99"),
        ("LM-BRANCH-CD", "X(4)"),
        ("LM-WAIVE-FLAG", "X"),
        ("FILLER-1", "X(3)"),
        ("LM-OFFICER-ID", "X(6)"),
        ("LM-LAST-PMT-DATE", "9(6)"),
        ("FILLER-2", "X(19)"),
    ],
)

# LNTRAN.cpy -- payment / reversal transactions.  40 bytes + LF.
LNTRAN = Layout(
    "LNTRAN",
    [
        ("TR-ACCT-NO", "9(10)"),
        ("TR-POST-DATE", "9(6)"),
        ("TR-SEQ-NO", "9(4)"),
        ("TR-TYPE", "X"),
        ("TR-AMOUNT", "S9(9)V99"),
        ("TR-VOID-FLAG", "X"),
        ("TR-CHANNEL", "X(3)"),
        ("FILLER", "X(4)"),
    ],
    terminator=b"\n",
)

# RATETBL.cpy -- header record then OCCURS DEPENDING ON tier rows.  40 bytes + LF.
RATETBL_HEADER = Layout(
    "RATETBL-HDR",
    [
        ("RH-REC-TYPE", "X"),
        ("RH-TIER-COUNT", "99"),
        ("RH-DESCRIPTION", "X(37)"),
    ],
    terminator=b"\n",
)

RATETBL_TIER = Layout(
    "RATETBL-TIER",
    [
        ("RT-REC-TYPE", "X"),
        ("RT-UPPER-BAL", "9(11)V99"),
        ("RT-ANNUAL-RATE", "9V9(5)"),
        ("RT-LATE-PCT", "9V9(4)"),
        ("RT-FEE-MIN", "9(5)V99"),
        ("RT-FEE-MAX", "9(5)V99"),
        ("FILLER", "X"),
    ],
    terminator=b"\n",
)

# LNOUT.cpy -- accrual output.  80 bytes + LF.  Detail and trailer share the record
# area (REDEFINES); LO-REC-TYPE / LT-REC-TYPE at the same position tells them apart.
LNOUT_DETAIL = Layout(
    "LNOUT-DETAIL",
    [
        ("LO-ACCT-NO", "9(10)"),
        ("LO-PRODUCT-CD", "X"),
        ("LO-ASOF-DATE", "9(8)"),
        ("LO-BALANCE", "S9(11)V99"),
        ("LO-ACCRUED-INT", "S9(9)V99"),
        ("LO-LATE-FEE", "9(7)V99"),
        ("LO-DAYS-LATE", "9(3)"),
        ("LO-STATUS", "X"),
        ("LO-RATE-TIER", "9"),
        ("LO-DAILY-RATE", "9V9(9)"),
        ("LO-ACCR-DAYS", "9(3)"),
        ("LO-REC-TYPE", "X"),
        ("FILLER", "X(9)"),
    ],
    terminator=b"\n",
)

LNOUT_TRAILER = Layout(
    "LNOUT-TRAILER",
    [
        ("LT-REC-COUNT", "9(7)"),
        ("LT-HASH-TOTAL", "9(11)"),
        ("LT-TOT-ACCRUED", "S9(11)V99"),
        ("LT-TOT-FEES", "9(11)V99"),
        ("LT-TOT-BALANCE", "S9(13)V99"),
        ("FILLER-1", "X(11)"),
        ("LT-REC-TYPE", "X"),
        ("FILLER-2", "X(9)"),
    ],
    terminator=b"\n",
)

REC_TYPE_DETAIL = "D"
REC_TYPE_TRAILER = "T"
REC_TYPE_OFFSET = LNOUT_DETAIL["LO-REC-TYPE"].offset

LAYOUTS = {
    "LNMAST": LNMAST,
    "LNTRAN": LNTRAN,
    "RATETBL-HDR": RATETBL_HEADER,
    "RATETBL-TIER": RATETBL_TIER,
    "LNOUT-DETAIL": LNOUT_DETAIL,
    "LNOUT-TRAILER": LNOUT_TRAILER,
}
