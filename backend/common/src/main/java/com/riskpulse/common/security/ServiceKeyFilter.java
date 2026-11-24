package com.riskpulse.common.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Second factor for service-to-service calls: {@code /internal/**} requires the shared
 * {@code X-Service-Key} (in addition to the propagated JWT). Fails closed when no key is configured.
 */
public class ServiceKeyFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Service-Key";
    private final byte[] expected;

    public ServiceKeyFilter(String serviceKey) {
        this.expected = serviceKey == null ? new byte[0] : serviceKey.getBytes(StandardCharsets.UTF_8);
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return !(path.equals("/internal") || path.startsWith("/internal/"));
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String provided = request.getHeader(HEADER);
        boolean ok = expected.length > 0
                && provided != null
                && MessageDigest.isEqual(expected, provided.getBytes(StandardCharsets.UTF_8));
        if (!ok) {
            ProblemJson.write(response, 401, "Unauthorized", "Missing or invalid service key");
            return;
        }
        chain.doFilter(request, response);
    }
}
