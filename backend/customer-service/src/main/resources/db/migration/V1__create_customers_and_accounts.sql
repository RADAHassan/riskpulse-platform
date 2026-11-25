CREATE TABLE customers (
                           user_id     UUID         PRIMARY KEY,
                           first_name  VARCHAR(100) NOT NULL,
                           last_name   VARCHAR(100) NOT NULL,
                           email       VARCHAR(255) NOT NULL,
                           phone       VARCHAR(30),
                           birth_date  DATE         NOT NULL,
                           address     VARCHAR(500),
                           status      VARCHAR(20)  NOT NULL,
                           created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
                           updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
                           version     BIGINT       NOT NULL DEFAULT 0,
                           CONSTRAINT uk_customers_email  UNIQUE (email),
                           CONSTRAINT ck_customers_status CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED'))
);

CREATE TABLE accounts (
                          id              UUID           PRIMARY KEY,
                          account_type    VARCHAR(20)    NOT NULL,
                          account_number  VARCHAR(34)    NOT NULL,
                          currency        VARCHAR(3)     NOT NULL,
                          balance         NUMERIC(19, 4) NOT NULL,
                          status          VARCHAR(20)    NOT NULL,
                          opened_at       TIMESTAMPTZ    NOT NULL DEFAULT now(),
                          version         BIGINT         NOT NULL DEFAULT 0,
                          customer_id     UUID           NOT NULL,
                          overdraft_limit NUMERIC(19, 4),
                          interest_rate   NUMERIC(7, 4),
                          minimum_balance NUMERIC(19, 4),

                          CONSTRAINT uk_accounts_number   UNIQUE (account_number),
                          CONSTRAINT fk_accounts_customer FOREIGN KEY (customer_id) REFERENCES customers (user_id),
                          CONSTRAINT ck_accounts_status   CHECK (status IN ('OPEN', 'FROZEN', 'CLOSED')),

    -- Contrepartie de l'héritage SINGLE_TABLE : on impose en base que chaque
    -- type de compte renseigne ses propres colonnes et seulement celles-là.
                          CONSTRAINT ck_accounts_type_columns CHECK (
                              (account_type = 'CHECKING'
                                  AND overdraft_limit IS NOT NULL AND overdraft_limit >= 0
                                  AND interest_rate IS NULL AND minimum_balance IS NULL
                                  AND balance >= -overdraft_limit)
                                  OR
                              (account_type = 'SAVINGS'
                                  AND interest_rate IS NOT NULL AND interest_rate >= 0
                                  AND minimum_balance IS NOT NULL AND minimum_balance >= 0
                                  AND overdraft_limit IS NULL)
                              )
);

-- PostgreSQL n'indexe pas automatiquement les clés étrangères.
CREATE INDEX idx_accounts_customer_id ON accounts (customer_id);