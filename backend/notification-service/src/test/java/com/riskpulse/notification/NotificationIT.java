package com.riskpulse.notification;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
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
class NotificationIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer postgres = new PostgreSQLContainer(DockerImageName
            .parse("postgres@sha256:f9cf3e1f0066f0eb0c48707d864f0ac5941e9ff454a072077d97a4d278d07d73")
            .asCompatibleSubstituteFor("postgres"));

    static final String KEY = "test-service-key-0123456789";

    @Autowired
    MockMvc mvc;

    static RequestPostProcessor as(String role, UUID customerId) {
        return jwt().jwt(j -> {
            j.subject(UUID.randomUUID().toString()).claim("roles", List.of(role));
            if (customerId != null) {
                j.claim("customer_id", customerId.toString());
            }
        }).authorities(new SimpleGrantedAuthority("ROLE_" + role));
    }

    private UUID create(UUID customerId, String subject) throws Exception {
        String body = "{\"type\":\"REVIEW_REQUIRED\",\"severity\":\"WARNING\",\"subject\":\"" + subject
                + "\",\"message\":\"Transaction needs a human decision\",\"customerId\":\"" + customerId + "\"}";
        String json = mvc.perform(post("/internal/notifications").with(as("ANALYST", null)).header("X-Service-Key", KEY)
                .contentType(MediaType.APPLICATION_JSON).content(body)).andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsString();
        return UUID.fromString(JsonPath.read(json, "$.id"));
    }

    @Test
    void internalCreationNeedsServiceKeyAndJwt() throws Exception {
        String body = "{\"type\":\"X\",\"severity\":\"INFO\",\"subject\":\"s\",\"message\":\"m\"}";
        mvc.perform(post("/internal/notifications").with(as("ANALYST", null)).contentType(MediaType.APPLICATION_JSON)
                .content(body)).andExpect(status().isUnauthorized());
        mvc.perform(post("/internal/notifications").header("X-Service-Key", KEY).contentType(MediaType.APPLICATION_JSON)
                .content(body)).andExpect(status().isUnauthorized());
    }

    @Test
    void customersOnlySeeTheirOwnNotifications() throws Exception {
        UUID alice = UUID.randomUUID();
        UUID bob = UUID.randomUUID();
        create(alice, "for-alice");
        create(bob, "for-bob");

        mvc.perform(get("/api/notifications").with(as("CUSTOMER", alice))).andExpect(status().isOk())
                .andExpect(jsonPath("$.totalElements").value(1))
                .andExpect(jsonPath("$.content[0].subject").value("for-alice"));
        mvc.perform(get("/api/notifications").with(as("ANALYST", null))).andExpect(status().isOk())
                .andExpect(jsonPath("$.totalElements").value(org.hamcrest.Matchers.greaterThanOrEqualTo(2)));
        mvc.perform(get("/api/notifications").with(as("CUSTOMER", null))).andExpect(status().isForbidden());
    }

    @Test
    void bolaCustomerCannotMarkAnotherCustomersNotificationAsRead() throws Exception {
        UUID alice = UUID.randomUUID();
        UUID bob = UUID.randomUUID();
        UUID bobsNotification = create(bob, "private-bob");

        mvc.perform(post("/api/notifications/" + bobsNotification + "/read").with(as("CUSTOMER", alice)))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/notifications/" + bobsNotification + "/read").with(as("CUSTOMER", bob)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.read").value(true));
        mvc.perform(post("/api/notifications/" + UUID.randomUUID() + "/read").with(as("ADMIN", null)))
                .andExpect(status().isNotFound());
    }

    @Test
    void unreadFilterAndValidation() throws Exception {
        UUID carol = UUID.randomUUID();
        UUID id = create(carol, "unread-1");
        mvc.perform(post("/api/notifications/" + id + "/read").with(as("CUSTOMER", carol))).andExpect(status().isOk());
        mvc.perform(get("/api/notifications").param("unreadOnly", "true").with(as("CUSTOMER", carol)))
                .andExpect(jsonPath("$.totalElements").value(0));
        mvc.perform(post("/internal/notifications").with(as("ANALYST", null)).header("X-Service-Key", KEY)
                .contentType(MediaType.APPLICATION_JSON).content("{\"type\":\"\",\"severity\":\"LOUD\"}"))
                .andExpect(status().isBadRequest());
    }
}
