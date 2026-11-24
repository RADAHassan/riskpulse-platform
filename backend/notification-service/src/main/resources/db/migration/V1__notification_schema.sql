CREATE TABLE notifications (
    id             UUID PRIMARY KEY,
    type           VARCHAR(40)   NOT NULL,
    severity       VARCHAR(10)   NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    subject        VARCHAR(200)  NOT NULL,
    message        VARCHAR(1000) NOT NULL,
    transaction_id UUID,
    customer_id    UUID,
    read           BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_notifications_customer ON notifications (customer_id, created_at DESC);
CREATE INDEX idx_notifications_created ON notifications (created_at DESC);
