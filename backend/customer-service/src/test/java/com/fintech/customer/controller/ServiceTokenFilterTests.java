package com.fintech.customer.controller;

import com.fintech.customer.config.InternalProperties;
import com.fintech.customer.config.ServiceTokenFilter;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import static org.assertj.core.api.Assertions.assertThat;

class ServiceTokenFilterTests {

    private MockHttpServletResponse call(String configuredToken, String path, String providedToken) throws Exception {
        var filter = new ServiceTokenFilter(new InternalProperties(configuredToken));
        var request = new MockHttpServletRequest("GET", path);
        request.setRequestURI(path);
        if (providedToken != null) {
            request.addHeader("X-Service-Token", providedToken);
        }
        var response = new MockHttpServletResponse();
        filter.doFilter(request, response, new MockFilterChain());
        return response;
    }

    @Test
    void internalPathWithoutToken_isRejected() throws Exception {
        assertThat(call("secret", "/internal/accounts/1", null).getStatus()).isEqualTo(401);
    }

    @Test
    void internalPathWithWrongToken_isRejected() throws Exception {
        assertThat(call("secret", "/internal/accounts/1", "nope").getStatus()).isEqualTo(401);
    }

    @Test
    void internalPathWithGoodToken_passes() throws Exception {
        assertThat(call("secret", "/internal/accounts/1", "secret").getStatus()).isEqualTo(200);
    }

    @Test
    void whenNoTokenIsConfigured_everythingIsRefused() throws Exception {
        assertThat(call("", "/internal/accounts/1", "").getStatus()).isEqualTo(401);
    }

    @Test
    void publicPaths_areNotConcerned() throws Exception {
        assertThat(call("secret", "/api/v1/customers/me", null).getStatus()).isEqualTo(200);
    }
}