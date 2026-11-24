package com.riskpulse.audit;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class AuditHashTest {

    @Test
    void canonicalDetailsAreOrderIndependentAndEscaped() {
        Map<String, Object> a = new LinkedHashMap<>();
        a.put("b", "2");
        a.put("a", "1\"x");
        Map<String, Object> b = new LinkedHashMap<>();
        b.put("a", "1\"x");
        b.put("b", "2");
        assertThat(AuditService.canonicalDetails(a)).isEqualTo(AuditService.canonicalDetails(b))
                .isEqualTo("{\"a\":\"1\\\"x\",\"b\":\"2\"}");
        assertThat(AuditService.canonicalDetails(null)).isEqualTo("{}");
    }

    @Test
    void hashChangesWhenAnyFieldChanges() {
        UUID id = UUID.randomUUID();
        Instant at = Instant.parse("2026-01-01T00:00:00Z");
        String base = AuditService.computeHash(AuditService.GENESIS, id, at, "a", "r", "ACT", "T", "1", "DECLINE", "m", "{}");
        assertThat(AuditService.computeHash(AuditService.GENESIS, id, at, "a", "r", "ACT", "T", "1", "APPROVE", "m", "{}"))
                .isNotEqualTo(base);
        assertThat(AuditService.computeHash("1".repeat(64), id, at, "a", "r", "ACT", "T", "1", "DECLINE", "m", "{}"))
                .isNotEqualTo(base);
        assertThat(AuditService.computeHash(AuditService.GENESIS, id, at, "a", "r", "ACT", "T", "1", "DECLINE", "m", "{}"))
                .isEqualTo(base).hasSize(64);
    }

    @Test
    void longDetailValuesAreBounded() {
        String huge = "x".repeat(5000);
        assertThat(AuditService.canonicalDetails(Map.of("k", huge)).length()).isLessThan(600);
    }
}
