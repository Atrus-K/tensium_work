      *****************************************************************
      *  LNOUT   - ACCRUAL OUTPUT                LRECL 80  RECFM FB  *
      *  VERSION 2  (2015-09)                                         *
      *                                                               *
      *  ONE DETAIL PER OPEN ACCOUNT FOLLOWED BY ONE TRAILER.  THE    *
      *  TRAILER REDEFINES THE DETAIL AREA; COL 71 (REC-TYPE) TELLS   *
      *  THEM APART.  SIGNED FIELDS ARE ZONED DECIMAL WITH TRAILING   *
      *  OVERPUNCH; UNSIGNED FIELDS ARE PLAIN DIGITS.                 *
      *****************************************************************
       01  LNOUT-DETAIL.
           05  LO-ACCT-NO              PIC 9(10).
           05  LO-PRODUCT-CD           PIC X.
           05  LO-ASOF-DATE            PIC 9(8).
           05  LO-BALANCE              PIC S9(11)V99.
           05  LO-ACCRUED-INT          PIC S9(9)V99.
           05  LO-LATE-FEE             PIC 9(7)V99.
           05  LO-DAYS-LATE            PIC 9(3).
           05  LO-STATUS               PIC X.
      *        C CURRENT  L LATE  D DELINQUENT  X SEVERE  W WRITE-OFF
           05  LO-RATE-TIER            PIC 9.
           05  LO-DAILY-RATE           PIC 9V9(9).
           05  LO-ACCR-DAYS            PIC 9(3).
           05  LO-REC-TYPE             PIC X.
      *        'D'
           05  FILLER                  PIC X(9).
       01  LNOUT-TRAILER REDEFINES LNOUT-DETAIL.
           05  LT-REC-COUNT            PIC 9(7).
           05  LT-HASH-TOTAL           PIC 9(11).
      *        SUM OF LO-ACCT-NO OVER DETAILS, MODULO 10**11
           05  LT-TOT-ACCRUED          PIC S9(11)V99.
           05  LT-TOT-FEES             PIC 9(11)V99.
           05  LT-TOT-BALANCE          PIC S9(13)V99.
           05  FILLER                  PIC X(11).
           05  LT-REC-TYPE             PIC X.
      *        'T'
           05  FILLER                  PIC X(9).
