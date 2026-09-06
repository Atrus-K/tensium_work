      *****************************************************************
      *  LNTRAN  - PERIOD PAYMENT / REVERSAL TRANSACTIONS             *
      *  LRECL 40  RECFM FB          VERSION 1  (2011-02)             *
      *                                                               *
      *  TR-AMOUNT IS SIGNED ZONED DECIMAL.  A NEGATIVE 'P' AMOUNT IS *
      *  A CORRECTION ENTRY (REDUCES THE AMOUNT PAID).                *
      *  RECORDS ARE IN CAPTURE ORDER, NOT POSTING ORDER.             *
      *****************************************************************
       01  LNTRAN-REC.
           05  TR-ACCT-NO              PIC 9(10).
           05  TR-POST-DATE            PIC 9(6).
           05  TR-SEQ-NO               PIC 9(4).
           05  TR-TYPE                 PIC X.
      *        P = PAYMENT   R = REVERSAL
           05  TR-AMOUNT               PIC S9(9)V99.
           05  TR-VOID-FLAG            PIC X.
      *        V = VOIDED, IGNORE
           05  TR-CHANNEL              PIC X(3).
           05  FILLER                  PIC X(4).
