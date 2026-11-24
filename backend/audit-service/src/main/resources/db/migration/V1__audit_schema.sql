-- Append-only, hash-chained audit trail.
CREATE TABLE audit_events (
    seq           BIGSERIAL    NOT NULL UNIQUE,
    id            UUID PRIMARY KEY,
    occurred_at   TIMESTAMPTZ  NOT NULL,
    actor         VARCHAR(100) NOT NULL,
    actor_role    VARCHAR(20)  NOT NULL,
    action        VARCHAR(80)  NOT NULL,
    resource_type VARCHAR(60)  NOT NULL,
    resource_id   VARCHAR(80)  NOT NULL,
    decision      VARCHAR(20),
    model_version VARCHAR(80),
    details       TEXT         NOT NULL DEFAULT '{}',
    prev_hash     VARCHAR(64)  NOT NULL,
    hash          VARCHAR(64)  NOT NULL
);

CREATE INDEX idx_audit_resource ON audit_events (resource_type, resource_id);
CREATE INDEX idx_audit_action ON audit_events (action);
CREATE INDEX idx_audit_occurred ON audit_events (occurred_at DESC);

-- Immutability enforced by the database itself, not only by the application.
CREATE FUNCTION audit_events_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only (% not allowed)', TG_OP USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_events_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();

CREATE TRIGGER audit_events_no_truncate
    BEFORE TRUNCATE ON audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION audit_events_immutable();
