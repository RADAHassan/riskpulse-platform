package com.riskpulse.gateway;

import java.nio.charset.StandardCharsets;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpResponse;
import reactor.core.publisher.Mono;

/** RFC 7807 responses written by the gateway itself (no stack trace, no echo of the request). */
final class Problems {

    private Problems() {
    }

    static Mono<Void> write(ServerHttpResponse response, HttpStatus status, String detail) {
        return write(response, status, detail, null);
    }

    static Mono<Void> write(ServerHttpResponse response, HttpStatus status, String detail, Long retryAfterSeconds) {
        if (response.isCommitted()) {
            return Mono.empty();
        }
        response.setStatusCode(status);
        response.getHeaders().set(HttpHeaders.CONTENT_TYPE, "application/problem+json");
        if (retryAfterSeconds != null) {
            response.getHeaders().set(HttpHeaders.RETRY_AFTER, String.valueOf(retryAfterSeconds));
        }
        String json = "{\"type\":\"about:blank\",\"title\":\"" + status.getReasonPhrase() + "\",\"status\":"
                + status.value() + ",\"detail\":\"" + detail.replace("\"", "'") + "\"}";
        DataBuffer buffer = response.bufferFactory().wrap(json.getBytes(StandardCharsets.UTF_8));
        return response.writeWith(Mono.just(buffer));
    }
}
