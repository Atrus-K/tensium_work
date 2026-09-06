# File transfer conventions for LNACCR01 datasets

The mainframe datasets are RECFM=FB. STEP020 of `legacy/JCL/LNACCR01.jcl` ships them to
the distributed side through MFT profiles that apply a **per-field conversion map**
generated from the copybooks. What lands on this side:

| Dataset | Profile | Record | Terminator | Notes |
|---------|---------|--------|------------|-------|
| LNMAST  | `LNMAST-MIXED`     | 120 bytes | none | DISPLAY fields converted to ASCII; `LM-PMT-DUE-AMT` (COMP-3) left as raw packed bytes. Open in binary mode. |
| LNTRAN  | `DISPLAY-ASCII-LF` | 40 bytes  | LF   | all DISPLAY |
| RATETBL | `DISPLAY-ASCII-LF` | 40 bytes  | LF   | header record then tier records |
| HOLIDAY | `DISPLAY-ASCII-LF` | text      | LF   | `YYYYMMDD DESCRIPTION`; lines starting `*` are comments |
| LNOUT   | `LNOUT-ASCII-LF`   | 80 bytes  | LF   | all DISPLAY; detail and trailer share the record area |

## Signed DISPLAY fields (zoned decimal)

COBOL `PIC S9(n)V9(m)` DISPLAY items carry the sign in the zone nibble of the **last**
digit. After EBCDIC→ASCII conversion that digit shows up as an *overpunch* character:

| digit | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|-------|---|---|---|---|---|---|---|---|---|---|
| positive (zone C) | `{` | `A` | `B` | `C` | `D` | `E` | `F` | `G` | `H` | `I` |
| negative (zone D) | `}` | `J` | `K` | `L` | `M` | `N` | `O` | `P` | `Q` | `R` |

So in a `S9(11)V99` field `000000001234N` is the 13 digits `0000000012345` with the
last digit 5 carrying a negative zone, i.e. **-123.45**, and `000000001234E` is
**+123.45**. Unsigned `PIC 9` fields are plain digits.

The mainframe writes *every* signed field with an overpunch, positive values included:
a zero balance is `000000000000{`, never `0000000000000`.

## Packed decimal (COMP-3)

Two digits per byte, sign in the low nibble of the last byte: `C` positive, `D`
negative, `F` unsigned. `PIC 9(9)V99 COMP-3` occupies 6 bytes (11 digits + sign).
Example: the 6 bytes `00 00 00 33 07 0F` are the digits `00000033070` with an
unsigned sign nibble, i.e. **330.70**.

## Dates

All LNMAST/LNTRAN dates are `YYMMDD`. LNACCR01 expands them with its own century
window (paragraph 2000-CENTURY-WINDOW); the as-of PARM and LNOUT's `LO-ASOF-DATE`
are `CCYYMMDD`.
