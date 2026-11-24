CREATE TABLE risk_assessments (
    id               UUID PRIMARY KEY,
    transaction_id   UUID           NOT NULL UNIQUE,
    customer_id      UUID           NOT NULL,
    amount           NUMERIC(18, 2) NOT NULL,
    probability      DOUBLE PRECISION,
    uncertainty      DOUBLE PRECISION,
    prediction       INTEGER,
    decision         VARCHAR(20)    NOT NULL CHECK (decision IN ('APPROVE', 'HUMAN_REVIEW', 'DECLINE')),
    reason           VARCHAR(100)   NOT NULL,
    fallback         BOOLEAN        NOT NULL DEFAULT FALSE,
    model_version    VARCHAR(80),
    registry_version VARCHAR(20),
    conformal_set    VARCHAR(20),
    created_at       TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE INDEX idx_assessments_customer ON risk_assessments (customer_id);
CREATE INDEX idx_assessments_decision ON risk_assessments (decision, created_at DESC);

CREATE TABLE review_cases (
    id             UUID PRIMARY KEY,
    assessment_id  UUID           NOT NULL REFERENCES risk_assessments (id),
    transaction_id UUID           NOT NULL UNIQUE,
    customer_id    UUID           NOT NULL,
    amount         NUMERIC(18, 2) NOT NULL,
    probability    DOUBLE PRECISION,
    uncertainty    DOUBLE PRECISION,
    model_version  VARCHAR(80),
    reason         VARCHAR(100)   NOT NULL,
    status         VARCHAR(10)    NOT NULL CHECK (status IN ('OPEN', 'APPROVED', 'REJECTED')),
    resolved_by    VARCHAR(100),
    resolved_at    TIMESTAMPTZ,
    note           VARCHAR(500),
    created_at     TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE INDEX idx_reviews_status ON review_cases (status, created_at);
