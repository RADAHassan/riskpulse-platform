package com.riskpulse.risk;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import io.micrometer.core.instrument.MeterRegistry;
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
class RiskIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer postgres = new PostgreSQLContainer(DockerImageName
            .parse("postgres@sha256:f9cf3e1f0066f0eb0c48707d864f0ac5941e9ff454a072077d97a4d278d07d73")
            .asCompatibleSubstituteFor("postgres"));

    static FakeServer ml;
    static FakeServer audit;
    static FakeServer notification;
    static FakeServer transaction;

    static {
        try {
            ml = new FakeServer("/predict");
            audit = new FakeServer("/internal/audit/events");
            notification = new FakeServer("/internal/notifications");
            transaction = new FakeServer("/internal/transactions");
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }

    @DynamicPropertySource
    static void urls(DynamicPropertyRegistry r) {
        r.add("riskpulse.ml.url", ml::url);
        r.add("riskpulse.audit.url", audit::url);
        r.add("riskpulse.notification.url", notification::url);
        r.add("riskpulse.transaction.url", transaction::url);
    }

    @AfterAll
    static void stopServers() {
        ml.close();
        audit.close();
        notification.close();
        transaction.close();
    }

    static final String KEY = "test-service-key-0123456789";
    static final List<Double> FEATURES = Collections.nCopies(28, 0.0);

    @Autowired
    MockMvc mvc;
    @Autowired
    MeterRegistry meters;
    @Autowired
    com.riskpulse.risk.ml.MlServingClient mlClient;

    @BeforeEach
    void reset() {
        mlClient.resetCircuit();
        audit.reset();
        notification.reset();
        transaction.reset();
        ml.reset();
    }

    static RequestPostProcessor as(String role, UUID customerId) {
        return jwt().jwt(j -> {
            j.subject(UUID.randomUUID().toString()).claim("roles", List.of(role)).claim("username", role.toLowerCase());
            if (customerId != null) {
                j.claim("customer_id", customerId.toString());
            }
        }).authorities(new SimpleGrantedAuthority("ROLE_" + role));
    }

    private String assessBody(UUID tx, UUID customer, String amount) {
        return "{\"transactionId\":\"" + tx + "\",\"customerId\":\"" + customer + "\",\"amount\":" + amount
                + ",\"features\":" + FEATURES + "}";
    }

    private String assess(UUID tx, UUID customer, RequestPostProcessor user) throws Exception {
        return mvc.perform(post("/internal/risk/assess").with(user).header("X-Service-Key", KEY)
                .contentType(MediaType.APPLICATION_JSON).content(assessBody(tx, customer, "149.99")))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
    }

    @Test
    void lowRiskIsApprovedAndAudited() throws Exception {
        ml.response = () -> FakeServer.ml("APPROVE", 0.001, 0.002, "[\"LEGIT\"]", false);
        UUID customer = UUID.randomUUID();
        String body = assess(UUID.randomUUID(), customer, as("CUSTOMER", customer));
        assertThat((String) JsonPath.read(body, "$.decision")).isEqualTo("APPROVE");
        assertThat((String) JsonPath.read(body, "$.modelVersion")).isEqualTo("riskpulse-29d-v2.0-canonical");
        assertThat(audit.bodies).hasSize(1);
        assertThat(audit.bodies.get(0)).contains("RISK_DECISION").contains("\"decision\":\"APPROVE\"")
                .contains("riskpulse-29d-v2.0-canonical");
        assertThat(notification.calls.get()).isZero();
    }

    @Test
    void confidentFraudIsDeclinedAndNotified() throws Exception {
        ml.response = () -> FakeServer.ml("DECLINE", 0.99, 0.02, "[\"FRAUD\"]", true);
        UUID customer = UUID.randomUUID();
        String body = assess(UUID.randomUUID(), customer, as("ADMIN", null));
        assertThat((String) JsonPath.read(body, "$.decision")).isEqualTo("DECLINE");
        assertThat(notification.bodies).hasSize(1);
        assertThat(notification.bodies.get(0)).contains("TRANSACTION_DECLINED").contains("CRITICAL");
    }

    @Test
    void uncertainPredictionIsNeverAutoDeclinedItGoesToTheReviewQueue() throws Exception {
        // ml-serving proposes DECLINE but the prediction is uncertain (0.45 >= 0.25) -> policy downgrades to review
        ml.response = () -> FakeServer.ml("DECLINE", 0.77, 0.45, "[\"LEGIT\",\"FRAUD\"]", false);
        UUID customer = UUID.randomUUID();
        UUID tx = UUID.randomUUID();
        String body = assess(tx, customer, as("ANALYST", null));
        assertThat((String) JsonPath.read(body, "$.decision")).isEqualTo("HUMAN_REVIEW");
        assertThat((String) JsonPath.read(body, "$.reason")).isEqualTo("uncertain_prediction_not_auto_declined");
        assertThat((String) JsonPath.read(body, "$.reviewId")).isNotBlank();
        assertThat(notification.bodies.get(0)).contains("REVIEW_REQUIRED");

        mvc.perform(get("/api/reviews").with(as("ANALYST", null))).andExpect(status().isOk())
                .andExpect(jsonPath("$.content[?(@.transactionId=='" + tx + "')].uncertainty").value(0.45));
    }

    @Test
    void mlOutageFallsBackToHumanReviewNeverApprove() throws Exception {
        ml.status = 500;
        UUID customer = UUID.randomUUID();
        String body = assess(UUID.randomUUID(), customer, as("ADMIN", null));
        assertThat((String) JsonPath.read(body, "$.decision")).isEqualTo("HUMAN_REVIEW");
        assertThat((Boolean) JsonPath.read(body, "$.fallback")).isTrue();
        assertThat((String) JsonPath.read(body, "$.reason")).isEqualTo("ml_serving_unavailable_fallback");
        assertThat(meters.get("riskpulse.risk.fallbacks").counter().count()).isGreaterThanOrEqualTo(1.0);
    }

    @Test
    void assessmentIsIdempotentPerTransaction() throws Exception {
        ml.response = () -> FakeServer.ml("APPROVE", 0.001, 0.002, "[\"LEGIT\"]", false);
        UUID tx = UUID.randomUUID();
        UUID customer = UUID.randomUUID();
        assess(tx, customer, as("ADMIN", null));
        int mlCalls = ml.calls.get();
        assess(tx, customer, as("ADMIN", null));
        assertThat(ml.calls.get()).isEqualTo(mlCalls);
    }

    @Test
    void analystResolvesAReviewAndTheTransactionIsUpdatedAndAudited() throws Exception {
        ml.response = () -> FakeServer.ml("HUMAN_REVIEW", 0.4, 0.8, "[\"LEGIT\",\"FRAUD\"]", true);
        UUID tx = UUID.randomUUID();
        String body = assess(tx, UUID.randomUUID(), as("ADMIN", null));
        String reviewId = JsonPath.read(body, "$.reviewId");

        mvc.perform(post("/api/reviews/" + reviewId + "/resolve").with(as("ANALYST", null))
                .contentType(MediaType.APPLICATION_JSON).content("{\"resolution\":\"APPROVE\",\"note\":\"customer called\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("APPROVED"))
                .andExpect(jsonPath("$.resolvedBy").value("analyst"));
        assertThat(transaction.bodies).anyMatch(b -> b.contains("APPROVE"));
        assertThat(audit.bodies).anyMatch(b -> b.contains("REVIEW_RESOLVED") && b.contains("customer called"));

        // a second resolution is a conflict
        mvc.perform(post("/api/reviews/" + reviewId + "/resolve").with(as("ANALYST", null))
                .contentType(MediaType.APPLICATION_JSON).content("{\"resolution\":\"REJECT\"}"))
                .andExpect(status().isConflict());
    }

    @Test
    void reviewQueueIsStaffOnly() throws Exception {
        UUID customer = UUID.randomUUID();
        mvc.perform(get("/api/reviews").with(as("CUSTOMER", customer))).andExpect(status().isForbidden());
        mvc.perform(post("/api/reviews/" + UUID.randomUUID() + "/resolve").with(as("CUSTOMER", customer))
                .contentType(MediaType.APPLICATION_JSON).content("{\"resolution\":\"APPROVE\"}"))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/reviews")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/risk/stats").with(as("CUSTOMER", customer))).andExpect(status().isForbidden());
    }

    @Test
    void bolaCustomerCannotAssessOrReadAnotherCustomersTransaction() throws Exception {
        ml.response = () -> FakeServer.ml("APPROVE", 0.001, 0.002, "[\"LEGIT\"]", false);
        UUID alice = UUID.randomUUID();
        UUID bob = UUID.randomUUID();
        mvc.perform(post("/internal/risk/assess").with(as("CUSTOMER", alice)).header("X-Service-Key", KEY)
                .contentType(MediaType.APPLICATION_JSON).content(assessBody(UUID.randomUUID(), bob, "10")))
                .andExpect(status().isForbidden());

        UUID tx = UUID.randomUUID();
        assess(tx, bob, as("ADMIN", null));
        mvc.perform(get("/api/risk/assessments/" + tx).with(as("CUSTOMER", alice))).andExpect(status().isForbidden());
        mvc.perform(get("/api/risk/assessments/" + tx).with(as("CUSTOMER", bob))).andExpect(status().isOk());
    }

    @Test
    void internalEndpointNeedsTheServiceKeyAndValidInput() throws Exception {
        mvc.perform(post("/internal/risk/assess").with(as("ADMIN", null)).contentType(MediaType.APPLICATION_JSON)
                .content(assessBody(UUID.randomUUID(), UUID.randomUUID(), "10"))).andExpect(status().isUnauthorized());
        mvc.perform(post("/internal/risk/assess").with(as("ADMIN", null)).header("X-Service-Key", KEY)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"transactionId\":\"" + UUID.randomUUID() + "\",\"customerId\":\"" + UUID.randomUUID()
                        + "\",\"amount\":-5,\"features\":[1,2,3]}")).andExpect(status().isBadRequest());
    }

    @Test
    void reviewQueueGaugeAndStatsReflectOpenCases() throws Exception {
        ml.response = () -> FakeServer.ml("HUMAN_REVIEW", 0.4, 0.8, "[\"LEGIT\",\"FRAUD\"]", true);
        assess(UUID.randomUUID(), UUID.randomUUID(), as("ADMIN", null));
        mvc.perform(get("/api/risk/stats").with(as("ANALYST", null))).andExpect(status().isOk())
                .andExpect(jsonPath("$.openReviews").value(org.hamcrest.Matchers.greaterThanOrEqualTo(1)));
        mvc.perform(get("/actuator/prometheus")).andExpect(status().isOk())
                .andExpect(result -> assertThat(result.getResponse().getContentAsString())
                        .contains("riskpulse_review_queue_size").contains("resilience4j_circuitbreaker_state"));
    }
}
