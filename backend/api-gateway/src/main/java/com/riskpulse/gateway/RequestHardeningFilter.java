package com.riskpulse.gateway;

import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

/**
 * First filter of the chain (runs before authentication):
 * <ul>
 *   <li>rejects oversized bodies (declared Content-Length) with 413 (OWASP API4);</li>
 *   <li>never lets {@code /internal/**} be reached from outside;</li>
 *   <li>strips client-supplied {@code X-Service-Key} so that the inter-service secret cannot be forged;</li>
 *   <li>normalises the correlation id {@code X-Request-Id}.</li>
 * </ul>
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestHardeningFilter implements WebFilter {

    public static final String REQUEST_ID = "X-Request-Id";
    private static final Pattern SAFE_ID = Pattern.compile("^[A-Za-z0-9\\-]{8,64}$");

    private final long maxBytes;

    public RequestHardeningFilter(@Value("${riskpulse.gateway.max-request-bytes:1048576}") long maxBytes) {
        this.maxBytes = maxBytes;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        var request = exchange.getRequest();
        String path = request.getPath().value();
        if (path.equals("/internal") || path.startsWith("/internal/")) {
            return Problems.write(exchange.getResponse(), HttpStatus.NOT_FOUND, "Resource not found");
        }
        if (request.getHeaders().getContentLength() > maxBytes) {
            return Problems.write(exchange.getResponse(), HttpStatus.CONTENT_TOO_LARGE, "Request body too large");
        }
        String incoming = request.getHeaders().getFirst(REQUEST_ID);
        String requestId = incoming != null && SAFE_ID.matcher(incoming).matches() ? incoming : UUID.randomUUID().toString();
        ServerWebExchange hardened = exchange.mutate()
                .request(r -> r.headers(h -> {
                    h.remove("X-Service-Key");
                    h.set(REQUEST_ID, requestId);
                }))
                .build();
        hardened.getResponse().getHeaders().set(REQUEST_ID, requestId);
        return chain.filter(hardened);
    }
}
