package com.fintech.customer.controller;

import com.fintech.customer.config.CorrelationIdFilter;
import com.fintech.customer.domain.CustomerStatus;
import com.fintech.customer.dto.CreateCustomerRequest;
import com.fintech.customer.dto.CustomerResponse;
import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import com.fintech.customer.exception.GlobalExceptionHandler;
import com.fintech.customer.security.CurrentUserArgumentResolver;
import com.fintech.customer.service.AccountService;
import com.fintech.customer.service.CustomerService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(MockitoExtension.class)
class ApiContractTests {

    static final String VALID_BODY = """
            {"firstName":"Amina","lastName":"Benali","phone":"+212612345678",
             "birthDate":"1995-04-12","address":"Tanger"}""";

    @Mock CustomerService customerService;
    @Mock AccountService accountService;

    MockMvc mvc;
    final UUID userId = UUID.randomUUID();

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders
                .standaloneSetup(new CustomerController(customerService), new AccountController(accountService))
                .setControllerAdvice(new GlobalExceptionHandler())
                .setCustomArgumentResolvers(new CurrentUserArgumentResolver())
                .addFilters(new CorrelationIdFilter())
                .build();
    }

    private MockHttpServletRequestBuilder as(MockHttpServletRequestBuilder request, String role) {
        return request.header("X-User-Id", userId.toString())
                .header("X-User-Role", role)
                .header("X-User-Email", "amina@example.com");
    }

    @Test
    void withoutIdentity_isUnauthenticated() throws Exception {
        mvc.perform(post("/api/v1/customers").contentType(MediaType.APPLICATION_JSON).content(VALID_BODY))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"));
    }

    @Test
    void analystCannotCreateAProfile() throws Exception {
        mvc.perform(as(post("/api/v1/customers"), "ANALYST")
                        .contentType(MediaType.APPLICATION_JSON).content(VALID_BODY))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }

    @Test
    void invalidBody_reportsAllViolationsTogether() throws Exception {
        String body = """
                {"firstName":"","lastName":"Benali","phone":"0612",
                 "birthDate":"1995-04-12","address":"Tanger"}""";

        mvc.perform(as(post("/api/v1/customers"), "CLIENT")
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.details[?(@.field=='firstName')]").exists())
                .andExpect(jsonPath("$.details[?(@.field=='phone')]").exists());
    }

    @Test
    void malformedJson_isABadRequest() throws Exception {
        mvc.perform(as(post("/api/v1/customers"), "CLIENT")
                        .contentType(MediaType.APPLICATION_JSON).content("{not json"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    @Test
    void validCreation_returns201WithLocation() throws Exception {
        var response = new CustomerResponse(userId, "Amina", "Benali", "amina@example.com", "+212612345678",
                LocalDate.of(1995, 4, 12), "Tanger", CustomerStatus.ACTIVE, Instant.now(), Instant.now());
        when(customerService.create(eq(userId), eq("amina@example.com"), any(CreateCustomerRequest.class)))
                .thenReturn(response);

        mvc.perform(as(post("/api/v1/customers"), "CLIENT")
                        .contentType(MediaType.APPLICATION_JSON).content(VALID_BODY))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", "/api/v1/customers/me"))
                .andExpect(jsonPath("$.userId").value(userId.toString()))
                .andExpect(jsonPath("$.status").value("ACTIVE"));
    }

    @Test
    void businessError_usesTheUniqueErrorFormat() throws Exception {
        when(customerService.create(any(), any(), any()))
                .thenThrow(new BusinessRuleException(ErrorCode.EMAIL_ALREADY_USED, "Email already used"));

        mvc.perform(as(post("/api/v1/customers"), "CLIENT")
                        .contentType(MediaType.APPLICATION_JSON).content(VALID_BODY))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.status").value(409))
                .andExpect(jsonPath("$.error").value("Conflict"))
                .andExpect(jsonPath("$.code").value("EMAIL_ALREADY_USED"))
                .andExpect(jsonPath("$.path").value("/api/v1/customers"))
                .andExpect(jsonPath("$.timestamp").exists())
                .andExpect(jsonPath("$.correlationId").exists());
    }

    @Test
    void pageSizeAboveTheLimit_isABadRequest() throws Exception {
        mvc.perform(as(get("/api/v1/customers").param("size", "500"), "ANALYST"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }

    @Test
    void adminCannotReadAnAccount_accordingToTheAccessMatrix() throws Exception {
        mvc.perform(as(get("/api/v1/accounts/" + UUID.randomUUID()), "ADMIN"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }
    @Test
    void invalidEmailInIdentity_isUnauthenticated() throws Exception {
        mvc.perform(post("/api/v1/customers")
                        .header("X-User-Id", userId.toString())
                        .header("X-User-Role", "CLIENT")
                        .header("X-User-Email", "CLIENT")
                        .contentType(MediaType.APPLICATION_JSON).content(VALID_BODY))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"));
    }

    @Test
    void correlationId_isKeptWhenSafe_andReplacedWhenSuspicious() throws Exception {
        mvc.perform(get("/api/v1/customers/me").header("X-Correlation-Id", "abc-123"))
                .andExpect(header().string("X-Correlation-Id", "abc-123"))
                .andExpect(jsonPath("$.correlationId").value("abc-123"));

        String replaced = mvc.perform(get("/api/v1/customers/me").header("X-Correlation-Id", "bad id\nINFO fake"))
                .andReturn().getResponse().getHeader("X-Correlation-Id");
        assertThat(replaced).matches("[A-Za-z0-9-]{1,64}").isNotEqualTo("bad id\nINFO fake");
    }
}