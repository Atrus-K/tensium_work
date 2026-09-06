      *****************************************************************
      *  LNMAST  - LOAN MASTER RECORD            LRECL 120  RECFM FB  *
      *  VERSION 3  (2019-06-14)                                      *
      *                                                               *
      *  V1 2011-02  ORIGINAL                                         *
      *  V2 2016-03  LM-BRANCH-CD REPLACED FILLER AT COL 82           *
      *  V3 2019-06  LM-WAIVE-FLAG CARVED OUT OF THE FILLER AT COL 86 *
      *              ('Y' = LATE FEE WAIVED BY BRANCH; ELSE SPACE)     *
      *                                                               *
      *  ALL DATES ARE YYMMDD; SEE 2000-CENTURY-WINDOW IN LNACCR01.   *
      *  LM-PRIN-BAL IS SIGNED ZONED DECIMAL (TRAILING OVERPUNCH);   *
      *  LM-PMT-DUE-AMT IS PACKED (COMP-3).                           *
      *****************************************************************
       01  LNMAST-REC.
           05  LM-ACCT-NO              PIC 9(10).
           05  LM-CUST-NAME            PIC X(30).
           05  LM-PRODUCT-CD           PIC X.
      *        M = MORTGAGE (30/360)   A = AUTO   P = PERSONAL (ACT/365)
           05  LM-STATUS               PIC X.
      *        A = ACTIVE   Z = CLOSED (EXCLUDED FROM ACCRUAL RUN)
           05  LM-ORIG-DATE            PIC 9(6).
           05  LM-DUE-DATE             PIC 9(6).
           05  LM-LAST-ACCR-DATE       PIC 9(6).
           05  LM-PRIN-BAL             PIC S9(11)V99.
           05  LM-PMT-DUE-AMT          PIC 9(9)V99 COMP-3.
           05  LM-GRACE-DAYS           PIC 99.
           05  LM-BRANCH-CD            PIC X(4).
           05  LM-WAIVE-FLAG           PIC X.
           05  FILLER                  PIC X(3).
           05  LM-OFFICER-ID           PIC X(6).
           05  LM-LAST-PMT-DATE        PIC 9(6).
           05  FILLER                  PIC X(19).
