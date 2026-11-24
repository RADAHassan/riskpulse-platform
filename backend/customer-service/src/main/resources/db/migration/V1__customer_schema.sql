CREATE TABLE customers (
    id          UUID PRIMARY KEY,
    first_name  VARCHAR(100) NOT NULL,
    last_name   VARCHAR(100) NOT NULL,
    email       VARCHAR(254) NOT NULL UNIQUE,
    country     VARCHAR(2)   NOT NULL,
    segment     VARCHAR(20)  NOT NULL CHECK (segment IN ('STANDARD', 'PREMIUM')),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_customers_last_name ON customers (lower(last_name));
