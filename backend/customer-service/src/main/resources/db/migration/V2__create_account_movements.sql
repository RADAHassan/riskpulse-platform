CREATE TABLE account_movements (
                                   transaction_id  UUID           PRIMARY KEY,
                                   kind            VARCHAR(20)    NOT NULL,
                                   fingerprint     VARCHAR(64)    NOT NULL,
                                   status          VARCHAR(20)    NOT NULL,
                                   balance_after   NUMERIC(19, 4) NOT NULL,
                                   applied_at      TIMESTAMPTZ    NOT NULL DEFAULT now(),
                                   CONSTRAINT ck_movements_kind CHECK (kind IN ('DEBIT', 'CREDIT', 'TRANSFER'))
);