package com.fintech.customer.config;

import com.fintech.customer.exception.ErrorCode;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;

/** Protege /internal/** : sans X-Service-Token valide, reponse 401 au format d'erreur unique. */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10) // apres CorrelationIdFilter
public class ServiceTokenFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Service-Token";

    private final byte[] expected;

    public ServiceTokenFilter(InternalProperties properties) {
        String token = properties.serviceToken();
        this.expected = token == null ? new byte[0] : token.getBytes(StandardCharsets.UTF_8);
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith("/internal/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String provided = request.getHeader(HEADER);
        boolean valid = expected.length > 0 && provided != null
                && MessageDigest.isEqual(expected, provided.getBytes(StandardCharsets.UTF_8));
        if (!valid) {
            response.setStatus(401);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.getWriter().write(errorJson(request));
            return;
        }
        chain.doFilter(request, response);
    }

    /** Memes champs que ErrorResponse (contrat 6.1). Les valeurs sont maitrisees ou nettoyees. */
    private String errorJson(HttpServletRequest request) {
        String correlationId = MDC.get("correlationId");
        return "{\"timestamp\":\"" + Instant.now() + "\","
                + "\"status\":401,\"error\":\"Unauthorized\","
                + "\"code\":\"" + ErrorCode.UNAUTHENTICATED.name() + "\","
                + "\"message\":\"Missing or invalid service token\","
                + "\"path\":\"" + escape(request.getRequestURI()) + "\""
                + (correlationId == null ? "" : ",\"correlationId\":\"" + escape(correlationId) + "\"")
                + "}";
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}