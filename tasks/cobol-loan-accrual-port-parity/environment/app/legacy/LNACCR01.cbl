       IDENTIFICATION DIVISION.
       PROGRAM-ID.    LNACCR01.
       AUTHOR.        LENDING SYSTEMS.
      *****************************************************************
      *  LNACCR01 - MONTHLY LOAN ACCRUAL / DELINQUENCY BATCH          *
      *                                                               *
      *  READS  : LNMAST  - LOAN MASTER (COPYBOOK LNMAST V3)          *
      *           LNTRAN  - PERIOD PAYMENTS / REVERSALS (LNTRAN)      *
      *           RATETBL - BALANCE TIER RATE TABLE (RATETBL)         *
      *           HOLIDAY - BANK HOLIDAY CALENDAR                     *
      *  WRITES : LNOUT   - ACCRUAL DETAIL + CONTROL TRAILER (LNOUT)  *
      *  PARM   : AS-OF DATE CCYYMMDD                                 *
      *                                                               *
      *  COMPILED WITH ARITH(EXTEND): INTERMEDIATE RESULTS OF EVERY   *
      *  COMPUTE ARE EXACT.  PRECISION IS LOST ONLY WHEN THE RESULT   *
      *  IS STORED INTO THE RECEIVING ITEM: TRUNCATED TO THE PICTURE  *
      *  SCALE UNLESS ROUNDED IS CODED (ROUNDED = HALF AWAY FROM 0).  *
      *  HIGH-ORDER DIGITS THAT DO NOT FIT ARE DROPPED.               *
      *                                                               *
      *  CHANGE LOG                                                   *
      *  2011-02  ORIGINAL                                            *
      *  2015-09  ADDED NEW-ACCOUNT LATE-FEE COURTESY WINDOW          *
      *  2019-06  LNMAST V3: LM-WAIVE-FLAG HONOURED IN 3500-          *
      *  2021-04  RATE TABLE TO OCCURS DEPENDING ON (MAX 9 TIERS)     *
      *****************************************************************
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT LNMAST-FILE  ASSIGN TO LNMAST.
           SELECT LNTRAN-FILE  ASSIGN TO LNTRAN.
           SELECT RATETBL-FILE ASSIGN TO RATETBL.
           SELECT HOLIDAY-FILE ASSIGN TO HOLIDAY.
           SELECT LNOUT-FILE   ASSIGN TO LNOUT.

       DATA DIVISION.
       FILE SECTION.
       FD  LNMAST-FILE RECORDING MODE F.
           COPY LNMAST.
       FD  LNTRAN-FILE RECORDING MODE F.
           COPY LNTRAN.
       FD  RATETBL-FILE RECORDING MODE F.
       01  RATETBL-REC                     PIC X(40).
       FD  HOLIDAY-FILE RECORDING MODE F.
       01  HOLIDAY-REC.
           05  HL-DATE                     PIC 9(8).
           05  FILLER                      PIC X(72).
       FD  LNOUT-FILE RECORDING MODE F.
           COPY LNOUT.

       WORKING-STORAGE SECTION.
       01  WS-PARM.
           05  WS-PARM-LEN                 PIC S9(4) COMP.
           05  WS-ASOF-DATE                PIC 9(8).
       01  WS-ASOF-INT                     PIC 9(8).
       01  WS-EOF-FLAGS.
           05  WS-MAST-EOF                 PIC X VALUE 'N'.
           05  WS-TRAN-EOF                 PIC X VALUE 'N'.
           05  WS-HOL-EOF                  PIC X VALUE 'N'.

           COPY RATETBL.

       01  WS-HOLIDAY-TABLE.
           05  WS-HOL-COUNT                PIC 9(3) VALUE 0.
           05  WS-HOL-DATE                 PIC 9(8) OCCURS 200 TIMES.
       01  WS-HOL-IX                       PIC 9(3).

      *    PAYMENT ACCUMULATOR - ONE SLOT PER MASTER ACCOUNT
       01  WS-PAID-TABLE.
           05  WS-PAID-COUNT               PIC 9(5) VALUE 0.
           05  WS-PAID-ENTRY OCCURS 20000 TIMES
               ASCENDING KEY IS WS-PAID-ACCT INDEXED BY PD-IX.
               10  WS-PAID-ACCT            PIC 9(10).
               10  WS-PAID-AMT             PIC S9(11)V99.

       01  WS-WORK-FIELDS.
           05  WS-NEW-BAL                  PIC S9(11)V99.
           05  WS-ACCT-PAID                PIC S9(11)V99.
           05  WS-BASIS                    PIC 9(3).
           05  WS-DAILY-RATE               PIC 9V9(9).
           05  WS-ACCRUED                  PIC S9(9)V99.
           05  WS-ACCR-DAYS                PIC S9(5).
           05  WS-DAYS-LATE                PIC S9(5).
           05  WS-ACCT-AGE                 PIC S9(7).
           05  WS-LATE-FEE                 PIC 9(7)V99.
           05  WS-TIER-IX                  PIC 99.
           05  WS-TIER-FOUND               PIC X.
           05  WS-STATUS                   PIC X.

       01  WS-DATE-WORK.
           05  WS-YYMMDD.
               10  WS-YY                   PIC 99.
               10  WS-MM                   PIC 99.
               10  WS-DD                   PIC 99.
           05  WS-CCYYMMDD.
               10  WS-CC                   PIC 99.
               10  WS-CCYY-REST            PIC 9(6).
           05  WS-CCYYMMDD-N REDEFINES WS-CCYYMMDD PIC 9(8).
           05  WS-DUE-ROLLED               PIC 9(8).
           05  WS-DUE-INT                  PIC 9(8).
           05  WS-DOW                      PIC 9.
           05  WS-ROLL-DONE                PIC X.
           05  WS-IS-HOLIDAY               PIC X.
           05  WS-D1-Y                     PIC 9(4).
           05  WS-D1-M                     PIC 99.
           05  WS-D1-D                     PIC 99.
           05  WS-D2-Y                     PIC 9(4).
           05  WS-D2-M                     PIC 99.
           05  WS-D2-D                     PIC 99.
           05  WS-DATE-1                   PIC 9(8).
           05  WS-DATE-2                   PIC 9(8).
           05  WS-DATE-1-X REDEFINES WS-DATE-1.
               10  WS-DATE-1-Y             PIC 9(4).
               10  WS-DATE-1-M             PIC 99.
               10  WS-DATE-1-D             PIC 99.
           05  WS-DATE-2-X REDEFINES WS-DATE-2.
               10  WS-DATE-2-Y             PIC 9(4).
               10  WS-DATE-2-M             PIC 99.
               10  WS-DATE-2-D             PIC 99.
           05  WS-ORIG-CCYYMMDD            PIC 9(8).
           05  WS-DUE-CCYYMMDD             PIC 9(8).
           05  WS-LACC-CCYYMMDD            PIC 9(8).

       01  WS-TOTALS.
           05  WS-REC-COUNT                PIC 9(7)  VALUE 0.
           05  WS-HASH-TOTAL               PIC 9(11) VALUE 0.
           05  WS-TOT-ACCRUED              PIC S9(11)V99 VALUE 0.
           05  WS-TOT-FEES                 PIC 9(11)V99  VALUE 0.
           05  WS-TOT-BALANCE              PIC S9(13)V99 VALUE 0.
           05  WS-SKIPPED-CLOSED           PIC 9(7)  VALUE 0.

       PROCEDURE DIVISION USING WS-PARM.
       0000-MAIN.
           MOVE WS-ASOF-DATE TO WS-CCYYMMDD-N
           COMPUTE WS-ASOF-INT = FUNCTION INTEGER-OF-DATE(WS-ASOF-DATE)
           PERFORM 1100-LOAD-HOLIDAYS
           PERFORM 1200-LOAD-RATE-TABLE
           PERFORM 1300-LOAD-TRANSACTIONS
           OPEN INPUT LNMAST-FILE
           OPEN OUTPUT LNOUT-FILE
           PERFORM 3000-PROCESS-MASTER UNTIL WS-MAST-EOF = 'Y'
           PERFORM 4000-WRITE-TRAILER
           CLOSE LNMAST-FILE LNOUT-FILE
           GOBACK.

      *----------------------------------------------------------------
       1100-LOAD-HOLIDAYS.
      *    HOLIDAY RECORDS: CCYYMMDD IN COLS 1-8.  COMMENT LINES
      *    START WITH '*' AND ARE SKIPPED.
           OPEN INPUT HOLIDAY-FILE
           PERFORM UNTIL WS-HOL-EOF = 'Y'
               READ HOLIDAY-FILE
                   AT END MOVE 'Y' TO WS-HOL-EOF
                   NOT AT END
                       IF HOLIDAY-REC(1:1) NOT = '*'
                          AND HOLIDAY-REC(1:8) IS NUMERIC
                           ADD 1 TO WS-HOL-COUNT
                           MOVE HL-DATE TO WS-HOL-DATE(WS-HOL-COUNT)
                       END-IF
               END-READ
           END-PERFORM
           CLOSE HOLIDAY-FILE.

      *----------------------------------------------------------------
       1200-LOAD-RATE-TABLE.
      *    FIRST RECORD IS THE HEADER (RH-TIER-COUNT), THEN ONE TIER
      *    RECORD PER OCCURS ENTRY.  TIERS ARE IN ASCENDING ORDER OF
      *    RT-UPPER-BAL; THE LAST TIER IS THE CATCH-ALL.
           OPEN INPUT RATETBL-FILE
           READ RATETBL-FILE INTO RATETBL-HEADER
           PERFORM VARYING WS-TIER-IX FROM 1 BY 1
                   UNTIL WS-TIER-IX > RH-TIER-COUNT
               READ RATETBL-FILE INTO RATETBL-TIER(WS-TIER-IX)
           END-PERFORM
           CLOSE RATETBL-FILE.

      *----------------------------------------------------------------
       1300-LOAD-TRANSACTIONS.
      *    NET PAID PER ACCOUNT FOR THE PERIOD:
      *      + PAYMENTS (TR-TYPE 'P')   - REVERSALS (TR-TYPE 'R')
      *    VOIDED ENTRIES (TR-VOID-FLAG 'V') ARE IGNORED.  TR-AMOUNT
      *    IS SIGNED; A NEGATIVE PAYMENT IS A CORRECTION ENTRY AND
      *    REDUCES THE AMOUNT PAID.
           OPEN INPUT LNTRAN-FILE
           PERFORM UNTIL WS-TRAN-EOF = 'Y'
               READ LNTRAN-FILE
                   AT END MOVE 'Y' TO WS-TRAN-EOF
                   NOT AT END
                       IF TR-VOID-FLAG NOT = 'V'
                           PERFORM 1310-POST-TO-PAID-TABLE
                       END-IF
               END-READ
           END-PERFORM
           CLOSE LNTRAN-FILE.

       1310-POST-TO-PAID-TABLE.
           PERFORM 1320-FIND-PAID-SLOT
           EVALUATE TR-TYPE
               WHEN 'P'
                   ADD TR-AMOUNT TO WS-PAID-AMT(PD-IX)
               WHEN 'R'
                   SUBTRACT TR-AMOUNT FROM WS-PAID-AMT(PD-IX)
           END-EVALUATE.

       1320-FIND-PAID-SLOT.
      *    SEQUENTIAL LOOK-UP; CREATE THE SLOT ON FIRST SIGHT.
           SET PD-IX TO 1
           SEARCH WS-PAID-ENTRY
               AT END
                   ADD 1 TO WS-PAID-COUNT
                   SET PD-IX TO WS-PAID-COUNT
                   MOVE TR-ACCT-NO TO WS-PAID-ACCT(PD-IX)
                   MOVE ZERO TO WS-PAID-AMT(PD-IX)
               WHEN WS-PAID-ACCT(PD-IX) = TR-ACCT-NO
                   CONTINUE
           END-SEARCH.

      *----------------------------------------------------------------
       3000-PROCESS-MASTER.
           READ LNMAST-FILE
               AT END
                   MOVE 'Y' TO WS-MAST-EOF
               NOT AT END
                   IF LM-STATUS = 'Z'
                       ADD 1 TO WS-SKIPPED-CLOSED
                   ELSE
                       PERFORM 3050-CONVERT-DATES
                       PERFORM 3100-APPLY-PAYMENTS
                       PERFORM 3200-FIND-TIER
                       PERFORM 3300-ACCRUE-INTEREST
                       PERFORM 3400-DAYS-LATE
                       PERFORM 3500-ASSESS-LATE-FEE
                       PERFORM 3600-SET-STATUS
                       PERFORM 3700-WRITE-DETAIL
                   END-IF
           END-READ.

      *----------------------------------------------------------------
       3050-CONVERT-DATES.
           MOVE LM-ORIG-DATE TO WS-YYMMDD
           PERFORM 2000-CENTURY-WINDOW
           MOVE WS-CCYYMMDD-N TO WS-ORIG-CCYYMMDD
           MOVE LM-DUE-DATE TO WS-YYMMDD
           PERFORM 2000-CENTURY-WINDOW
           MOVE WS-CCYYMMDD-N TO WS-DUE-CCYYMMDD
           MOVE LM-LAST-ACCR-DATE TO WS-YYMMDD
           PERFORM 2000-CENTURY-WINDOW
           MOVE WS-CCYYMMDD-N TO WS-LACC-CCYYMMDD.

       2000-CENTURY-WINDOW.
      *    YYMMDD -> CCYYMMDD.  YY 50-99 ARE THE 1900S, 00-49 THE 2000S.
           IF WS-YY > 49
               MOVE 19 TO WS-CC
           ELSE
               MOVE 20 TO WS-CC
           END-IF
           MOVE WS-YYMMDD TO WS-CCYY-REST.

      *----------------------------------------------------------------
       3100-APPLY-PAYMENTS.
           MOVE ZERO TO WS-ACCT-PAID
           PERFORM VARYING PD-IX FROM 1 BY 1
                   UNTIL PD-IX > WS-PAID-COUNT
               IF WS-PAID-ACCT(PD-IX) = LM-ACCT-NO
                   MOVE WS-PAID-AMT(PD-IX) TO WS-ACCT-PAID
               END-IF
           END-PERFORM
      *    THE BALANCE MAY GO NEGATIVE (CREDIT BALANCE AFTER OVERPAYMENT)
           COMPUTE WS-NEW-BAL = LM-PRIN-BAL - WS-ACCT-PAID.

      *----------------------------------------------------------------
       3200-FIND-TIER.
      *    FIRST TIER WHOSE UPPER BOUND IS NOT EXCEEDED (INCLUSIVE).
      *    FALLS THROUGH TO THE LAST TIER.
           MOVE 'N' TO WS-TIER-FOUND
           PERFORM VARYING WS-TIER-IX FROM 1 BY 1
                   UNTIL WS-TIER-IX > RH-TIER-COUNT
                      OR WS-TIER-FOUND = 'Y'
               IF WS-NEW-BAL <= RT-UPPER-BAL(WS-TIER-IX)
                   MOVE 'Y' TO WS-TIER-FOUND
               ELSE
                   IF WS-TIER-IX = RH-TIER-COUNT
                       MOVE 'Y' TO WS-TIER-FOUND
                   END-IF
               END-IF
           END-PERFORM
           SUBTRACT 1 FROM WS-TIER-IX.

      *----------------------------------------------------------------
       3300-ACCRUE-INTEREST.
      *    MORTGAGE PRODUCTS ('M') ACCRUE ON 30/360 (US); ALL OTHERS ON
      *    ACTUAL DAYS / 365.  WS-DAILY-RATE IS NOT ROUNDED: THE
      *    QUOTIENT IS TRUNCATED TO NINE DECIMALS BEFORE THE MULTIPLY.
      *    INTEREST ACCRUES ON POSITIVE BALANCES ONLY.
           MOVE WS-LACC-CCYYMMDD TO WS-DATE-1
           MOVE WS-ASOF-DATE     TO WS-DATE-2
           IF LM-PRODUCT-CD = 'M'
               MOVE 360 TO WS-BASIS
               PERFORM 2300-DAYS-360
           ELSE
               MOVE 365 TO WS-BASIS
               PERFORM 2200-DAYS-ACTUAL
           END-IF
           COMPUTE WS-DAILY-RATE =
                   RT-ANNUAL-RATE(WS-TIER-IX) / WS-BASIS
           IF WS-NEW-BAL > ZERO
               COMPUTE WS-ACCRUED ROUNDED =
                       WS-NEW-BAL * WS-DAILY-RATE * WS-ACCR-DAYS
           ELSE
               MOVE ZERO TO WS-ACCRUED
           END-IF.

       2200-DAYS-ACTUAL.
           COMPUTE WS-ACCR-DAYS = FUNCTION INTEGER-OF-DATE(WS-DATE-2)
                                - FUNCTION INTEGER-OF-DATE(WS-DATE-1).

       2300-DAYS-360.
      *    30/360 US CONVENTION WITH BOTH END-OF-MONTH ADJUSTMENTS.
           MOVE WS-DATE-1-Y TO WS-D1-Y
           MOVE WS-DATE-1-M TO WS-D1-M
           MOVE WS-DATE-1-D TO WS-D1-D
           MOVE WS-DATE-2-Y TO WS-D2-Y
           MOVE WS-DATE-2-M TO WS-D2-M
           MOVE WS-DATE-2-D TO WS-D2-D
           IF WS-D1-D = 31
               MOVE 30 TO WS-D1-D
           END-IF
           IF WS-D2-D = 31 AND WS-D1-D >= 30
               MOVE 30 TO WS-D2-D
           END-IF
           COMPUTE WS-ACCR-DAYS = 360 * (WS-D2-Y - WS-D1-Y)
                                +  30 * (WS-D2-M - WS-D1-M)
                                +       (WS-D2-D - WS-D1-D).

      *----------------------------------------------------------------
       3400-DAYS-LATE.
      *    DAYS FROM THE (BUSINESS-DAY ROLLED) DUE DATE TO THE AS-OF
      *    DATE.  NOT YET DUE -> 0.  PAID IN FULL DURING THE PERIOD
      *    (NET PAID >= PAYMENT DUE) -> 0.
           MOVE WS-DUE-CCYYMMDD TO WS-DUE-ROLLED
           PERFORM 2400-ROLL-BUSINESS-DAY
           COMPUTE WS-DAYS-LATE = WS-ASOF-INT
                                - FUNCTION INTEGER-OF-DATE(WS-DUE-ROLLED)
           IF WS-DAYS-LATE < ZERO
               MOVE ZERO TO WS-DAYS-LATE
           END-IF
           IF WS-ACCT-PAID >= LM-PMT-DUE-AMT
               MOVE ZERO TO WS-DAYS-LATE
           END-IF.

       2400-ROLL-BUSINESS-DAY.
      *    ADVANCE WS-DUE-ROLLED WHILE IT FALLS ON SATURDAY, SUNDAY OR
      *    A DATE IN THE HOLIDAY TABLE.  INTEGER-OF-DATE(1601-01-01)=1
      *    IS A MONDAY, SO MOD 7 GIVES 1=MON .. 5=FRI, 6=SAT, 0=SUN.
           MOVE 'N' TO WS-ROLL-DONE
           PERFORM UNTIL WS-ROLL-DONE = 'Y'
               COMPUTE WS-DUE-INT =
                       FUNCTION INTEGER-OF-DATE(WS-DUE-ROLLED)
               COMPUTE WS-DOW = FUNCTION MOD(WS-DUE-INT, 7)
               PERFORM 2410-LOOKUP-HOLIDAY
               IF WS-DOW = 0 OR WS-DOW = 6 OR WS-IS-HOLIDAY = 'Y'
                   COMPUTE WS-DUE-ROLLED =
                           FUNCTION DATE-OF-INTEGER(WS-DUE-INT + 1)
               ELSE
                   MOVE 'Y' TO WS-ROLL-DONE
               END-IF
           END-PERFORM.

       2410-LOOKUP-HOLIDAY.
           MOVE 'N' TO WS-IS-HOLIDAY
           PERFORM VARYING WS-HOL-IX FROM 1 BY 1
                   UNTIL WS-HOL-IX > WS-HOL-COUNT
               IF WS-HOL-DATE(WS-HOL-IX) = WS-DUE-ROLLED
                   MOVE 'Y' TO WS-IS-HOLIDAY
               END-IF
           END-PERFORM.

      *----------------------------------------------------------------
       3500-ASSESS-LATE-FEE.
      *    FEE ONLY WHEN PAST THE GRACE PERIOD (STRICTLY MORE DAYS LATE
      *    THAN LM-GRACE-DAYS), NOT WAIVED (LM-WAIVE-FLAG 'Y', LNMAST
      *    V3), AND THE ACCOUNT IS OLDER THAN THE 90-DAY NEW-ACCOUNT
      *    COURTESY WINDOW.  FEE = TIER PCT OF THE PAYMENT DUE, ROUNDED,
      *    THEN HELD WITHIN THE TIER'S MIN / MAX.
           COMPUTE WS-ACCT-AGE = WS-ASOF-INT
                               - FUNCTION INTEGER-OF-DATE(WS-ORIG-CCYYMMDD)
           MOVE ZERO TO WS-LATE-FEE
           IF WS-DAYS-LATE > LM-GRACE-DAYS
               IF LM-WAIVE-FLAG NOT = 'Y'
                   IF WS-ACCT-AGE > 90
                       COMPUTE WS-LATE-FEE ROUNDED =
                               LM-PMT-DUE-AMT * RT-LATE-PCT(WS-TIER-IX)
                       IF WS-LATE-FEE < RT-FEE-MIN(WS-TIER-IX)
                           MOVE RT-FEE-MIN(WS-TIER-IX) TO WS-LATE-FEE
                       END-IF
                       IF WS-LATE-FEE > RT-FEE-MAX(WS-TIER-IX)
                           MOVE RT-FEE-MAX(WS-TIER-IX) TO WS-LATE-FEE
                       END-IF
                   END-IF
               END-IF
           END-IF.

      *----------------------------------------------------------------
       3600-SET-STATUS.
      *    FIRST TRUE WHEN WINS; ALL COMPARISONS ARE STRICT.
           EVALUATE TRUE
               WHEN WS-DAYS-LATE > 90
                   MOVE 'W' TO WS-STATUS
               WHEN WS-DAYS-LATE > 60
                   MOVE 'X' TO WS-STATUS
               WHEN WS-DAYS-LATE > 30
                   MOVE 'D' TO WS-STATUS
               WHEN WS-DAYS-LATE > LM-GRACE-DAYS
                   MOVE 'L' TO WS-STATUS
               WHEN OTHER
                   MOVE 'C' TO WS-STATUS
           END-EVALUATE.

      *----------------------------------------------------------------
       3700-WRITE-DETAIL.
           MOVE SPACES           TO LNOUT-DETAIL
           MOVE LM-ACCT-NO       TO LO-ACCT-NO
           MOVE LM-PRODUCT-CD    TO LO-PRODUCT-CD
           MOVE WS-ASOF-DATE     TO LO-ASOF-DATE
           MOVE WS-NEW-BAL       TO LO-BALANCE
           MOVE WS-ACCRUED       TO LO-ACCRUED-INT
           MOVE WS-LATE-FEE      TO LO-LATE-FEE
           MOVE WS-DAYS-LATE     TO LO-DAYS-LATE
           MOVE WS-STATUS        TO LO-STATUS
           MOVE WS-TIER-IX       TO LO-RATE-TIER
           MOVE WS-DAILY-RATE    TO LO-DAILY-RATE
           MOVE WS-ACCR-DAYS     TO LO-ACCR-DAYS
           MOVE 'D'              TO LO-REC-TYPE
           WRITE LNOUT-DETAIL
           ADD 1 TO WS-REC-COUNT
           COMPUTE WS-HASH-TOTAL =
                   FUNCTION MOD(WS-HASH-TOTAL + LM-ACCT-NO, 100000000000)
           ADD WS-ACCRUED  TO WS-TOT-ACCRUED
           ADD WS-LATE-FEE TO WS-TOT-FEES
           ADD WS-NEW-BAL  TO WS-TOT-BALANCE.

      *----------------------------------------------------------------
       4000-WRITE-TRAILER.
           MOVE SPACES           TO LNOUT-TRAILER
           MOVE WS-REC-COUNT     TO LT-REC-COUNT
           MOVE WS-HASH-TOTAL    TO LT-HASH-TOTAL
           MOVE WS-TOT-ACCRUED   TO LT-TOT-ACCRUED
           MOVE WS-TOT-FEES      TO LT-TOT-FEES
           MOVE WS-TOT-BALANCE   TO LT-TOT-BALANCE
           MOVE 'T'              TO LT-REC-TYPE
           WRITE LNOUT-TRAILER.
