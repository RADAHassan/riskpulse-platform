package com.riskpulse.transaction;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import java.io.IOException;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
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
class TransactionIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer postgres = new PostgreSQLContainer(DockerImageName
            .parse("postgres@sha256:f9cf3e1f0066f0eb0c48707d864f0ac5941e9ff454a072077d97a4d278d07d73")
            .asCompatibleSubstituteFor("postgres"));

    static FakeServer riskService;
    static FakeServer audit;

    static {
        try {
            riskService = new FakeServer("/internal/risk/assess");
            audit = new FakeServer("/internal/audit/events");
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }

    @DynamicPropertySource
    static void urls(DynamicPropertyRegistry r) {
        r.add("riskpulse.risk.url", riskService::url);
        r.add("riskpulse.audit.url", audit::url);
    }

    @AfterAll
    static void stop() {
        riskService.close();
        audit.close();
    }

    static final String KEY = "test-service-key-0123456789";
    static final List<Double> FEATURES = Collections.nCopies(28, 0.0);

    @Autowired
    MockMvc mvc;
    @Autowired
    RiskClient riskClient;

    @BeforeEach
    void reset() {
        riskClient.resetCircuit();
        riskService.reset();
        audit.reset();
        riskService.response = () -> FakeServer.risk("APPROVE", "low_risk", 0.001, 0.002, false);
    }

    static RequestPostProcessor as(String role, UUID customerId) {
        return jwt().jwt(j -> {
            j.subject(UUID.randomUUID().toString()).claim("roles", List.of(role)).claim("username", role.toLowerCase());
            if (customerId != null) {
                j.claim("customer_id", customerId.toString());
            }
        }).authorities(new SimpleGrantedAuthority("ROLE_" + role));
    }

    private static String body(UUID customer, String amount) {
        return "{" + (customer == null ? "" : "\"customerId\":\"" + customer + "\",") + "\"amount\":" + amount
                + ",\"merchant\":\"ACME\",\"features\":" + FEATURES + "}";
    }

    private String submit(UUID customer, RequestPostProcessor user) throws Exception {
        return mvc.perform(post("/api/transactions").with(user).contentType(MediaType.APPLICATION_JSON)
                .content(body(customer, "42.10"))).andExpect(status().isCreated()).andReturn().getResponse()
                .getContentAsString();
    }

    @Test
    void customerSubmitsATransactionAndReceivesTheRiskDecision() throws Exception {
        UUID customer = UUID.randomUUID();
        String json = submit(null, as("CUSTOMER", customer)); // customerId defaults to the token's customer
        assertThat((String) JsonPath.read(json, "$.status")).isEqualTo("APPROVED");
        assertThat((String) JsonPath.read(json, "$.customerId")).isEqualTo(customer.toString());
        assertThat((String) JsonPath.read(json, "$.modelVersion")).isEqualTo("riskpulse-29d-v2.0-canonical");
        assertThat(riskService.bodies.get(0)).contains("\"transactionId\"").contains("\"features\"");
        assertThat(audit.bodies).anyMatch(b -> b.contains("TRANSACTION_SUBMITTED") && b.contains("APPROVE"));
    }

    @Test
    void humanReviewAndDeclineMapToStatuses() throws Exception {
        riskService.response = () -> FakeServer.risk("HUMAN_REVIEW", "uncertain", 0.6, 0.8, false);
        assertThat((String) JsonPath.read(submit(UUID.randomUUID(), as("ADMIN", null)), "$.status")).isEqualTo("UNDER_REVIEW");
        riskService.response = () -> FakeServer.risk("DECLINE", "fraud", 0.99, 0.02, false);
        assertThat((String) JsonPath.read(submit(UUID.randomUUID(), as("ADMIN", null)), "$.status")).isEqualTo("DECLINED");
    }

    @Test
    void bolaCustomerCannotSubmitForOrReadAnotherCustomer() throws Exception {
        UUID alice = UUID.randomUUID();
        UUID bob = UUID.randomUUID();
        mvc.perform(post("/api/transactions").with(as("CUSTOMER", alice)).contentType(MediaType.APPLICATION_JSON)
                .content(body(bob, "10"))).andExpect(status().isForbidden());
        assertThat(riskService.calls.get()).isZero();

        String bobsTx = submit(bob, as("CUSTOMER", bob));
        String id = JsonPath.read(bobsTx, "$.id");
        mvc.perform(get("/api/transactions/" + id).with(as("CUSTOMER", alice))).andExpect(status().isForbidden());
        mvc.perform(get("/api/transactions/" + id).with(as("CUSTOMER", bob))).andExpect(status().isOk());
        mvc.perform(get("/api/transactions/" + id).with(as("ANALYST", null))).andExpect(status().isOk());
    }

    @Test
    void listIsScopedToTheCustomerAndTheScopeCannotBeOverridden() throws Exception {
        UUID alice = UUID.randomUUID();
        UUID bob = UUID.randomUUID();
        submit(alice, as("CUSTOMER", alice));
        submit(bob, as("CUSTOMER", bob));
        mvc.perform(get("/api/transactions").param("customerId", bob.toString()).with(as("CUSTOMER", alice)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.totalElements").value(1))
                .andExpect(jsonPath("$.content[0].customerId").value(alice.toString()));
        mvc.perform(get("/api/transactions").param("customerId", bob.toString()).with(as("ANALYST", null)))
                .andExpect(jsonPath("$.totalElements").value(1))
                .andExpect(jsonPath("$.content[0].customerId").value(bob.toString()));
    }

    @Test
    void riskServiceOutageNeverApproves() throws Exception {
        riskService.status = 503;
        String json = submit(UUID.randomUUID(), as("ADMIN", null));
        assertThat((String) JsonPath.read(json, "$.status")).isEqualTo("PENDING_RISK");
        assertThat((String) JsonPath.read(json, "$.decision")).isEqualTo("HUMAN_REVIEW");
        assertThat((String) JsonPath.read(json, "$.reason")).isEqualTo("risk_service_unavailable");
    }

    @Test
    void simulatorIsAdminOnlyAndRunsThePipeline() throws Exception {
        riskService.response = () -> FakeServer.risk("APPROVE", "low_risk", 0.001, 0.002, false);
        mvc.perform(post("/api/transactions/simulate").with(as("ANALYST", null)).contentType(MediaType.APPLICATION_JSON)
                .content("{\"count\":3}")).andExpect(status().isForbidden());
        mvc.perform(post("/api/transactions/simulate").with(as("ADMIN", null)).contentType(MediaType.APPLICATION_JSON)
                .content("{\"count\":5,\"fraudRatio\":0.4}")).andExpect(status().isOk())
                .andExpect(jsonPath("$.processed").value(5)).andExpect(jsonPath("$.approved").value(5));
        assertThat(riskService.calls.get()).isEqualTo(5);
        mvc.perform(post("/api/transactions/simulate").with(as("ADMIN", null)).contentType(MediaType.APPLICATION_JSON)
                .content("{\"count\":5000}")).andExpect(status().isBadRequest());
    }

    @Test
    void internalDecisionCallbackNeedsServiceKeyAndUpdatesTheTransaction() throws Exception {
        riskService.response = () -> FakeServer.risk("HUMAN_REVIEW", "uncertain", 0.6, 0.8, false);
        String id = JsonPath.read(submit(UUID.randomUUID(), as("ADMIN", null)), "$.id");
        String payload = "{\"decision\":\"APPROVE\"}";
        mvc.perform(put("/internal/transactions/" + id + "/decision").with(as("ANALYST", null))
                .contentType(MediaType.APPLICATION_JSON).content(payload)).andExpect(status().isUnauthorized());
        mvc.perform(put("/internal/transactions/" + id + "/decision").with(as("ANALYST", null)).header("X-Service-Key", KEY)
                .contentType(MediaType.APPLICATION_JSON).content(payload)).andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("APPROVED")).andExpect(jsonPath("$.reason").value("human_review_approve"));
        mvc.perform(put("/internal/transactions/" + id + "/decision").with(as("ANALYST", null)).header("X-Service-Key", KEY)
                .contentType(MediaType.APPLICATION_JSON).content("{\"decision\":\"MAYBE\"}")).andExpect(status().isBadRequest());
    }

    @Test
    void invalidPayloadsAreRejectedAndMetricsAreExposed() throws Exception {
        mvc.perform(post("/api/transactions").with(as("ADMIN", null)).contentType(MediaType.APPLICATION_JSON)
                .content("{\"customerId\":\"" + UUID.randomUUID() + "\",\"amount\":-1,\"features\":[1,2]}"))
                .andExpect(status().isBadRequest());
        mvc.perform(post("/api/transactions").contentType(MediaType.APPLICATION_JSON).content(body(UUID.randomUUID(), "1")))
                .andExpect(status().isUnauthorized());
        submit(UUID.randomUUID(), as("ADMIN", null));
        mvc.perform(get("/actuator/prometheus")).andExpect(status().isOk()).andExpect(result ->
                assertThat(result.getResponse().getContentAsString()).contains("riskpulse_transactions_total{")
                        .contains("decision=\"APPROVE\""));
    }
}
