package com.riskpulse.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import com.nimbusds.jwt.SignedJWT;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AuthIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer postgres = new PostgreSQLContainer(DockerImageName
            .parse("postgres@sha256:f9cf3e1f0066f0eb0c48707d864f0ac5941e9ff454a072077d97a4d278d07d73")
            .asCompatibleSubstituteFor("postgres"));

    @Autowired
    MockMvc mvc;

    private MvcResult login(String user, String password) throws Exception {
        return mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"" + user + "\",\"password\":\"" + password + "\"}")).andReturn();
    }

    private String json(MvcResult r, String path) throws Exception {
        return JsonPath.read(r.getResponse().getContentAsString(), path);
    }

    @Test
    void adminLogsInAndGetsAShortLivedRs256TokenWithRoleClaims() throws Exception {
        MvcResult r = login("admin", "AdminPassw0rd!2026");
        assertThat(r.getResponse().getStatus()).isEqualTo(200);

        SignedJWT jwt = SignedJWT.parse(json(r, "$.accessToken"));
        assertThat(jwt.getHeader().getAlgorithm().getName()).isEqualTo("RS256");
        assertThat(jwt.getHeader().getKeyID()).isNotBlank();
        assertThat(jwt.getJWTClaimsSet().getIssuer()).isEqualTo("riskpulse-auth");
        assertThat(jwt.getJWTClaimsSet().getStringListClaim("roles")).containsExactly("ADMIN");
        long ttl = jwt.getJWTClaimsSet().getExpirationTime().getTime() - jwt.getJWTClaimsSet().getIssueTime().getTime();
        assertThat(ttl).isEqualTo(15 * 60 * 1000L);
        assertThat(json(r, "$.tokenType")).isEqualTo("Bearer");
    }

    @Test
    void jwksIsPublicAndContainsNoPrivateMaterial() throws Exception {
        String body = mvc.perform(get("/.well-known/jwks.json")).andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        assertThat(body).contains("\"kty\":\"RSA\"").contains("\"kid\"");
        assertThat(body).doesNotContain("\"d\":").doesNotContain("\"p\":").doesNotContain("\"q\":");
    }

    @Test
    void wrongPasswordAndUnknownUserGiveTheSameAnswer() throws Exception {
        MvcResult wrong = login("analyst", "not-the-password");
        MvcResult unknown = login("ghost-user", "whatever-123456");
        assertThat(wrong.getResponse().getStatus()).isEqualTo(401);
        assertThat(unknown.getResponse().getStatus()).isEqualTo(401);
        assertThat(json(wrong, "$.detail")).isEqualTo(json(unknown, "$.detail"));
    }

    @Test
    void accountIsLockedAfterRepeatedFailures() throws Exception {
        String victim = "victim-" + UUID.randomUUID().toString().substring(0, 8);
        String token = json(login("admin", "AdminPassw0rd!2026"), "$.accessToken");
        mvc.perform(post("/api/auth/users").header("Authorization", "Bearer " + token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"" + victim + "\",\"password\":\"CorrectHorse!Battery9\",\"role\":\"ANALYST\"}"))
                .andExpect(status().isCreated());

        for (int i = 0; i < 3; i++) {
            assertThat(login(victim, "bad-password-" + i).getResponse().getStatus()).isEqualTo(401);
        }
        // locked now: even the right password is refused
        assertThat(login(victim, "CorrectHorse!Battery9").getResponse().getStatus()).isEqualTo(423);
    }

    @Test
    void refreshTokenIsRotatedAndReplayRevokesTheSession() throws Exception {
        MvcResult first = login("analyst", "AnalystPassw0rd!2026");
        String refresh1 = json(first, "$.refreshToken");

        MvcResult second = mvc.perform(post("/api/auth/refresh").contentType(MediaType.APPLICATION_JSON)
                .content("{\"refreshToken\":\"" + refresh1 + "\"}")).andExpect(status().isOk()).andReturn();
        String refresh2 = json(second, "$.refreshToken");
        assertThat(refresh2).isNotEqualTo(refresh1);

        // replaying the already rotated token is treated as theft
        mvc.perform(post("/api/auth/refresh").contentType(MediaType.APPLICATION_JSON)
                .content("{\"refreshToken\":\"" + refresh1 + "\"}")).andExpect(status().isUnauthorized());
        // ... and the whole family is dead, including the legitimate newest token
        mvc.perform(post("/api/auth/refresh").contentType(MediaType.APPLICATION_JSON)
                .content("{\"refreshToken\":\"" + refresh2 + "\"}")).andExpect(status().isUnauthorized());
    }

    @Test
    void logoutRevokesTheRefreshToken() throws Exception {
        String refresh = json(login("analyst", "AnalystPassw0rd!2026"), "$.refreshToken");
        mvc.perform(post("/api/auth/logout").contentType(MediaType.APPLICATION_JSON)
                .content("{\"refreshToken\":\"" + refresh + "\"}")).andExpect(status().isNoContent());
        mvc.perform(post("/api/auth/refresh").contentType(MediaType.APPLICATION_JSON)
                .content("{\"refreshToken\":\"" + refresh + "\"}")).andExpect(status().isUnauthorized());
    }

    @Test
    void onlyAdminCanCreateUsers() throws Exception {
        String analystToken = json(login("analyst", "AnalystPassw0rd!2026"), "$.accessToken");
        String body = "{\"username\":\"intruder\",\"password\":\"AnotherLongPassw0rd!\",\"role\":\"ADMIN\"}";
        mvc.perform(post("/api/auth/users").header("Authorization", "Bearer " + analystToken)
                .contentType(MediaType.APPLICATION_JSON).content(body)).andExpect(status().isForbidden());
        mvc.perform(post("/api/auth/users").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void customerRoleRequiresACustomerId() throws Exception {
        String token = json(login("admin", "AdminPassw0rd!2026"), "$.accessToken");
        mvc.perform(post("/api/auth/users").header("Authorization", "Bearer " + token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"cust-no-id\",\"password\":\"CorrectHorse!Battery9\",\"role\":\"CUSTOMER\"}"))
                .andExpect(status().isBadRequest());

        UUID customerId = UUID.randomUUID();
        MvcResult created = mvc.perform(post("/api/auth/users").header("Authorization", "Bearer " + token)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"cust-ok\",\"password\":\"CorrectHorse!Battery9\",\"role\":\"CUSTOMER\","
                        + "\"customerId\":\"" + customerId + "\"}")).andExpect(status().isCreated()).andReturn();
        assertThat(json(created, "$.customerId")).isEqualTo(customerId.toString());

        SignedJWT jwt = SignedJWT.parse(json(login("cust-ok", "CorrectHorse!Battery9"), "$.accessToken"));
        assertThat(jwt.getJWTClaimsSet().getStringClaim("customer_id")).isEqualTo(customerId.toString());
        assertThat(jwt.getJWTClaimsSet().getStringListClaim("roles")).isEqualTo(List.of("CUSTOMER"));
    }

    @Test
    void validationErrorsAreRfc7807AndDoNotEchoInput() throws Exception {
        mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"\",\"password\":\"s3cr3t-value-leak\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors").isArray())
                .andExpect(result -> assertThat(result.getResponse().getContentAsString())
                        .doesNotContain("s3cr3t-value-leak"));
    }

    @Test
    void meRequiresAValidToken() throws Exception {
        mvc.perform(get("/api/auth/me")).andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status").value(401));
        mvc.perform(get("/api/auth/me").header("Authorization", "Bearer not.a.jwt")).andExpect(status().isUnauthorized());
        String token = json(login("analyst", "AnalystPassw0rd!2026"), "$.accessToken");
        mvc.perform(get("/api/auth/me").header("Authorization", "Bearer " + token)).andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("ANALYST"));
    }
}
