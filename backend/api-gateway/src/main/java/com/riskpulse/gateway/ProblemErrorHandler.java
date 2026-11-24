package com.riskpulse.gateway;

import io.netty.handler.timeout.ReadTimeoutException;
import java.net.ConnectException;
import java.util.concurrent.TimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.webflux.error.ErrorWebExceptionHandler;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/** Gateway-level failures (no route, downstream down/slow) as RFC 7807, without internals. */
@Component
@Order(-2)
public class ProblemErrorHandler implements ErrorWebExceptionHandler {

    private static final Logger LOG = LoggerFactory.getLogger(ProblemErrorHandler.class);

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
        HttpStatus status;
        String detail;
        if (ex instanceof ResponseStatusException rse && HttpStatus.resolve(rse.getStatusCode().value()) != null
                && rse.getStatusCode().value() < 500) {
            status = HttpStatus.valueOf(rse.getStatusCode().value());
            detail = status == HttpStatus.NOT_FOUND ? "Resource not found" : status.getReasonPhrase();
        } else if (hasCause(ex, ConnectException.class)) {
            status = HttpStatus.SERVICE_UNAVAILABLE;
            detail = "Upstream service unavailable";
        } else if (hasCause(ex, TimeoutException.class) || hasCause(ex, ReadTimeoutException.class)) {
            status = HttpStatus.GATEWAY_TIMEOUT;
            detail = "Upstream service timed out";
        } else if (ex instanceof ResponseStatusException rse && rse.getStatusCode().value() == 503) {
            status = HttpStatus.SERVICE_UNAVAILABLE;
            detail = "Upstream service unavailable";
        } else {
            status = HttpStatus.INTERNAL_SERVER_ERROR;
            detail = "Internal server error";
            LOG.error("Unhandled gateway error", ex);
        }
        return Problems.write(exchange.getResponse(), status, detail);
    }

    private static boolean hasCause(Throwable t, Class<? extends Throwable> type) {
        for (Throwable c = t; c != null; c = c.getCause()) {
            if (type.isInstance(c)) {
                return true;
            }
            if (c.getCause() == c) {
                break;
            }
        }
        return false;
    }
}
