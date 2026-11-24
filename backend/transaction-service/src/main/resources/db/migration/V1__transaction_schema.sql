CREATE TABLE transactions (
    id            UUID PRIMARY KEY,
    customer_id   UUID             NOT NULL,
    amount        NUMERIC(18, 2)   NOT NULL CHECK (amount >= 0),
    currency      VARCHAR(3)       NOT NULL DEFAULT 'EUR',
    merchant      VARCHAR(100),
    features      DOUBLE PRECISION[] NOT NULL,
    status        VARCHAR(20)      NOT NULL,
    decision      VARCHAR(20),
    reason        VARCHAR(100),
    probability   DOUBLE PRECISION,
    uncertainty   DOUBLE PRECISION,
    model_version VARCHAR(80),
    simulated     BOOLEAN          NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ      NOT NULL DEFAULT now(),
    decided_at    TIMESTAMPTZ
);

CREATE INDEX idx_transactions_customer ON transactions (customer_id, created_at DESC);
CREATE INDEX idx_transactions_status ON transactions (status, created_at DESC);
CREATE INDEX idx_transactions_created ON transactions (created_at DESC);
