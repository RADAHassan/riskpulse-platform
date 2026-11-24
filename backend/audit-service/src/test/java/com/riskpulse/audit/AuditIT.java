package com.riskpulse.audit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AuditIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer postgres = new PostgreSQLContainer(DockerImageName
            .parse("postgres@sha256:f9cf3e1f0066f0eb0c48707d864f0ac5941e9ff454a072077d97a4d278d07d73")
            .asCompatibleSubstituteFor("postgres"));

    static final String KEY = "test-service-key-0123456789";

    @Autowired
    MockMvc mvc;
    @Autowired
    AuditService service;
    @Autowired
    JdbcTemplate jdbc;

    static RequestPostProcessor as(String role) {
        return jwt().jwt(j -> j.subject(UUID.randomUUID().toString()).claim("roles", List.of(role)))
                .authorities(new SimpleGrantedAuthority("ROLE_" + role));
    }

    private static AuditController.AuditEventRequest event(String action, String resource) {
        return new AuditController.AuditEventRequest("risk-service", "SERVICE", action, "Transaction", resource, "DECLINE",
                "model-1", java.util.Map.of("probability", 0.97, "note", "line1\nline2 \"quoted\""));
    }

    @Test
    void internalEndpointRequiresTheServiceKey() throws Exception {
        String body = "{\"actor\":\"auth\",\"actorRole\":\"ANONYMOUS\",\"action\":\"LOGIN_FAILURE\",\"resourceType\":\"User\","
                + "\"resourceId\":\"u1\"}";
        mvc.perform(post("/internal/audit/events").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/internal/audit/events").header("X-Service-Key", "wrong")
                .contentType(MediaType.APPLICATION_JSON).content(body)).andExpect(status().isUnauthorized());
        mvc.perform(post("/internal/audit/events").header("X-Service-Key", KEY)
                .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.hash").isString());
    }

    @Test
    void eventsFormAVerifiableHashChain() {
        for (int i = 0; i < 5; i++) {
            service.append(event("DECISION_RECORDED", "tx-chain-" + i));
        }
        AuditService.Verification v = service.verify();
        assertThat(v.valid()).isTrue();
        assertThat(v.checked()).isGreaterThanOrEqualTo(5);
    }

    @Test
    void databaseRefusesUpdateDeleteAndTruncate() {
        service.append(event("DECISION_RECORDED", "tx-immutable"));
        assertThatThrownBy(() -> jdbc.update("update audit_events set actor = 'attacker'"))
                .rootCause().hasMessageContaining("append-only");
        assertThatThrownBy(() -> jdbc.update("delete from audit_events"))
                .rootCause().hasMessageContaining("append-only");
        assertThatThrownBy(() -> jdbc.execute("truncate table audit_events")).rootCause().hasMessageContaining("append-only");
    }

    @Test
    void tamperingWithTheStorageIsDetectedByVerification() {
        service.append(event("DECISION_RECORDED", "tx-tamper-1"));
        service.append(event("DECISION_RECORDED", "tx-tamper-2"));
        assertThat(service.verify().valid()).isTrue();
        try {
            // an attacker with raw DB access disables the trigger and edits history
            jdbc.execute("alter table audit_events disable trigger audit_events_no_update_delete");
            jdbc.update("update audit_events set decision = 'APPROVE' where resource_id = 'tx-tamper-1'");
            AuditService.Verification v = service.verify();
            assertThat(v.valid()).isFalse();
            assertThat(v.reason()).contains("modified");
            assertThat(v.firstBrokenSeq()).isNotNull();
        } finally {
            jdbc.execute("update audit_events set decision = 'DECLINE' where resource_id = 'tx-tamper-1'");
            jdbc.execute("alter table audit_events enable trigger audit_events_no_update_delete");
        }
        assertThat(service.verify().valid()).isTrue();
    }

    @Test
    void concurrentWritersNeverForkTheChain() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(8);
        try {
            List<Future<?>> futures = new java.util.ArrayList<>();
            for (int i = 0; i < 40; i++) {
                int n = i;
                futures.add(pool.submit(() -> service.append(event("CONCURRENT", "tx-par-" + n))));
            }
            for (Future<?> f : futures) {
                f.get();
            }
        } finally {
            pool.shutdown();
        }
        assertThat(service.verify().valid()).isTrue();
    }

    @Test
    void readAccessIsRoleRestrictedAndVerifyIsAdminOnly() throws Exception {
        service.append(event("DECISION_RECORDED", "tx-read"));
        mvc.perform(get("/api/audit/events").with(as("CUSTOMER"))).andExpect(status().isForbidden());
        mvc.perform(get("/api/audit/events")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/audit/events").param("resourceId", "tx-read").with(as("ANALYST")))
                .andExpect(status().isOk()).andExpect(jsonPath("$.content[0].resourceId").value("tx-read"))
                .andExpect(jsonPath("$.content[0].details").value(org.hamcrest.Matchers.containsString("quoted")));
        mvc.perform(get("/api/audit/events/verify").with(as("ANALYST"))).andExpect(status().isForbidden());
        mvc.perform(get("/api/audit/events/verify").with(as("ADMIN"))).andExpect(status().isOk())
                .andExpect(jsonPath("$.valid").value(true));
    }

    @Test
    void invalidEventsAreRejected() throws Exception {
        mvc.perform(post("/internal/audit/events").header("X-Service-Key", KEY).contentType(MediaType.APPLICATION_JSON)
                .content("{\"actor\":\"\",\"action\":\"X\"}")).andExpect(status().isBadRequest());
    }
}
