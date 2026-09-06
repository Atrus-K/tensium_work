      *****************************************************************
      *  RATETBL - BALANCE TIER RATE TABLE       LRECL 40  RECFM FB  *
      *  VERSION 2  (2021-04)  OCCURS DEPENDING ON, MAX 9 TIERS       *
      *                                                               *
      *  RECORD 1 IS THE HEADER; RECORDS 2..N+1 ARE THE TIERS IN      *
      *  ASCENDING RT-UPPER-BAL ORDER.  A BALANCE BELONGS TO THE      *
      *  FIRST TIER WHOSE UPPER BOUND IT DOES NOT EXCEED; THE LAST    *
      *  TIER IS THE CATCH-ALL.  TIER NUMBERS ARE 1-BASED.            *
      *****************************************************************
       01  RATETBL-HEADER.
           05  RH-REC-TYPE             PIC X.
      *        'H'
           05  RH-TIER-COUNT           PIC 99.
           05  RH-DESCRIPTION          PIC X(37).
       01  RATETBL-TIERS.
           05  RATETBL-TIER OCCURS 1 TO 9 TIMES
                            DEPENDING ON RH-TIER-COUNT.
               10  RT-REC-TYPE         PIC X.
      *            'T'
               10  RT-UPPER-BAL        PIC 9(11)V99.
               10  RT-ANNUAL-RATE      PIC 9V9(5).
               10  RT-LATE-PCT         PIC 9V9(4).
               10  RT-FEE-MIN          PIC 9(5)V99.
               10  RT-FEE-MAX          PIC 9(5)V99.
               10  FILLER              PIC X.
