package com.riskpulse.customer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
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
class CustomerIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer postgres = new PostgreSQLContainer(DockerImageName
            .parse("postgres@sha256:f9cf3e1f0066f0eb0c48707d864f0ac5941e9ff454a072077d97a4d278d07d73")
            .asCompatibleSubstituteFor("postgres"));

    @Autowired
    MockMvc mvc;

    static RequestPostProcessor as(String role, UUID customerId) {
        return jwt().jwt(j -> {
            j.subject(UUID.randomUUID().toString()).claim("roles", List.of(role)).claim("username", role.toLowerCase());
            if (customerId != null) {
                j.claim("customer_id", customerId.toString());
            }
        }).authorities(new SimpleGrantedAuthority("ROLE_" + role));
    }

    private UUID createCustomer(String email) throws Exception {
        String body = mvc.perform(post("/api/customers").with(as("ADMIN", null)).contentType(MediaType.APPLICATION_JSON)
                .content("{\"firstName\":\"Ada\",\"lastName\":\"Lovelace\",\"email\":\"" + email
                        + "\",\"country\":\"FR\",\"segment\":\"PREMIUM\"}"))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        return UUID.fromString(JsonPath.read(body, "$.id"));
    }

    @Test
    void analystCanCreateAndListButCustomerCannot() throws Exception {
        UUID id = createCustomer("ada-" + UUID.randomUUID() + "@example.com");
        mvc.perform(get("/api/customers").with(as("ANALYST", null))).andExpect(status().isOk())
                .andExpect(jsonPath("$.content").isArray());
        mvc.perform(get("/api/customers").with(as("CUSTOMER", id))).andExpect(status().isForbidden());
        mvc.perform(post("/api/customers").with(as("CUSTOMER", id)).contentType(MediaType.APPLICATION_JSON)
                .content("{\"firstName\":\"X\",\"lastName\":\"Y\",\"email\":\"x@y.fr\",\"country\":\"FR\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void bolaCustomerCannotReadOrUpdateAnotherCustomer() throws Exception {
        UUID alice = createCustomer("alice-" + UUID.randomUUID() + "@example.com");
        UUID bob = createCustomer("bob-" + UUID.randomUUID() + "@example.com");

        mvc.perform(get("/api/customers/" + alice).with(as("CUSTOMER", alice))).andExpect(status().isOk());
        mvc.perform(get("/api/customers/" + bob).with(as("CUSTOMER", alice))).andExpect(status().isForbidden());
        mvc.perform(put("/api/customers/" + bob).with(as("CUSTOMER", alice)).contentType(MediaType.APPLICATION_JSON)
                .content("{\"firstName\":\"Hacked\",\"lastName\":\"Bob\",\"country\":\"US\"}"))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/customers/" + bob).with(as("ANALYST", null)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.firstName").value("Ada"));
        mvc.perform(get("/api/customers/me").with(as("CUSTOMER", alice))).andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(alice.toString()));
    }

    @Test
    void customerCanUpdateOwnProfileButNotDelete() throws Exception {
        UUID carol = createCustomer("carol-" + UUID.randomUUID() + "@example.com");
        mvc.perform(put("/api/customers/" + carol).with(as("CUSTOMER", carol)).contentType(MediaType.APPLICATION_JSON)
                .content("{\"firstName\":\"Carol\",\"lastName\":\"Danvers\",\"country\":\"US\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.lastName").value("Danvers"));
        mvc.perform(delete("/api/customers/" + carol).with(as("CUSTOMER", carol))).andExpect(status().isForbidden());
        mvc.perform(delete("/api/customers/" + carol).with(as("ANALYST", null))).andExpect(status().isForbidden());
        mvc.perform(delete("/api/customers/" + carol).with(as("ADMIN", null))).andExpect(status().isNoContent());
        mvc.perform(get("/api/customers/" + carol).with(as("ADMIN", null))).andExpect(status().isNotFound());
    }

    @Test
    void duplicateEmailIsRejectedAndInputIsValidated() throws Exception {
        String email = "dup-" + UUID.randomUUID() + "@example.com";
        createCustomer(email);
        mvc.perform(post("/api/customers").with(as("ADMIN", null)).contentType(MediaType.APPLICATION_JSON)
                .content("{\"firstName\":\"A\",\"lastName\":\"B\",\"email\":\"" + email + "\",\"country\":\"FR\"}"))
                .andExpect(status().isConflict());
        mvc.perform(post("/api/customers").with(as("ADMIN", null)).contentType(MediaType.APPLICATION_JSON)
                .content("{\"firstName\":\"\",\"lastName\":\"B\",\"email\":\"not-an-email\",\"country\":\"France\"}"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.errors.length()").value(3));
    }

    @Test
    void anonymousAndMalformedAccessIsRejected() throws Exception {
        mvc.perform(get("/api/customers")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/customers/not-a-uuid").with(as("ADMIN", null))).andExpect(status().isBadRequest());
        String body = mvc.perform(get("/api/customers/" + UUID.randomUUID()).with(as("ADMIN", null)))
                .andExpect(status().isNotFound()).andReturn().getResponse().getContentAsString();
        assertThat(body).doesNotContain("Exception").doesNotContain("at com.");
    }

    @Test
    void healthAndPrometheusAreOpenForTheCluster() throws Exception {
        mvc.perform(get("/actuator/health/liveness")).andExpect(status().isOk());
        mvc.perform(get("/actuator/prometheus")).andExpect(status().isOk());
    }
}
