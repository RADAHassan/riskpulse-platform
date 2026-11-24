package com.riskpulse.customer;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.riskpulse.common.audit.AuditClient;
import com.riskpulse.common.security.CommonSecurityConfig;
import com.riskpulse.common.web.ApiExceptionHandler;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

/** Slice test: controller + real security configuration, repository mocked (ownership rule is checked BEFORE any data access). */
@WebMvcTest(CustomerController.class)
@Import({CommonSecurityConfig.class, ApiExceptionHandler.class})
class CustomerControllerWebTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    CustomerRepository repository;

    @MockitoBean
    AuditClient audit;

    @MockitoBean
    JwtDecoder jwtDecoder;

    private static RequestPostProcessor customer(UUID customerId) {
        return jwt().jwt(j -> j.subject(UUID.randomUUID().toString()).claim("roles", List.of("CUSTOMER"))
                .claim("customer_id", customerId.toString())).authorities(new SimpleGrantedAuthority("ROLE_CUSTOMER"));
    }

    @Test
    void ownerGetsHisRecord() throws Exception {
        UUID id = UUID.randomUUID();
        when(repository.findById(id)).thenReturn(Optional.of(new Customer("Ada", "L", "a@example.com", "FR", null)));
        mvc.perform(get("/api/customers/" + id).with(customer(id))).andExpect(status().isOk())
                .andExpect(jsonPath("$.firstName").value("Ada"));
    }

    @Test
    void anotherCustomerIsRefusedWithoutTouchingTheDatabase() throws Exception {
        UUID victim = UUID.randomUUID();
        mvc.perform(get("/api/customers/" + victim).with(customer(UUID.randomUUID())))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.title").value("Forbidden"));
        verifyNoInteractions(repository);
    }

    @Test
    void methodSecurityBlocksCustomerFromListing() throws Exception {
        mvc.perform(get("/api/customers").with(customer(UUID.randomUUID()))).andExpect(status().isForbidden());
        verifyNoInteractions(repository);
    }

    @Test
    void anonymousIsUnauthorizedWithProblemJson() throws Exception {
        mvc.perform(get("/api/customers/" + UUID.randomUUID())).andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status").value(401));
        when(repository.existsByEmailIgnoreCase(any())).thenReturn(false);
    }
}
