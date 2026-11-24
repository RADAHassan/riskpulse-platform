package com.riskpulse.gateway;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.net.InetSocketAddress;
import java.security.Principal;
import java.time.Duration;
import java.util.function.LongSupplier;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

/**
 * Rate limiting (OWASP API4): per client IP, per authenticated user, and a tighter per-IP budget on the
 * credential endpoints (brute force). In-memory per gateway replica: with N replicas the effective limit is
 * at most N times the configured one (documented trade-off, no Redis dependency).
 */
@Component
public class RateLimitFilter implements GlobalFilter, Ordered {

    private final Cache<String, TokenBucket> buckets = Caffeine.newBuilder()
            .maximumSize(100_000).expireAfterAccess(Duration.ofMinutes(10)).build();
    private final int ipPerMinute;
    private final int userPerMinute;
    private final int authPerMinute;
    private final boolean trustForwardedFor;
    private final LongSupplier clock;

    @Autowired
    public RateLimitFilter(@Value("${riskpulse.gateway.rate-limit.ip-per-minute:300}") int ipPerMinute,
                           @Value("${riskpulse.gateway.rate-limit.user-per-minute:600}") int userPerMinute,
                           @Value("${riskpulse.gateway.rate-limit.auth-per-minute:20}") int authPerMinute,
                           @Value("${riskpulse.gateway.trust-forwarded-for:false}") boolean trustForwardedFor) {
        this(ipPerMinute, userPerMinute, authPerMinute, trustForwardedFor, System::nanoTime);
    }

    RateLimitFilter(int ipPerMinute, int userPerMinute, int authPerMinute, boolean trustForwardedFor, LongSupplier clock) {
        this.ipPerMinute = ipPerMinute;
        this.userPerMinute = userPerMinute;
        this.authPerMinute = authPerMinute;
        this.trustForwardedFor = trustForwardedFor;
        this.clock = clock;
    }

    @Override
    public int getOrder() {
        return -200;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String ip = clientIp(exchange);
        String path = exchange.getRequest().getPath().value();

        if (path.equals("/api/auth/login") || path.equals("/api/auth/refresh")) {
            TokenBucket auth = bucket("auth:" + ip, authPerMinute);
            if (!auth.tryConsume(clock.getAsLong())) {
                return reject(exchange, auth);
            }
        }
        TokenBucket ipBucket = bucket("ip:" + ip, ipPerMinute);
        if (!ipBucket.tryConsume(clock.getAsLong())) {
            return reject(exchange, ipBucket);
        }
        return exchange.getPrincipal().map(Principal::getName).defaultIfEmpty("").flatMap(user -> {
            if (!user.isEmpty()) {
                TokenBucket userBucket = bucket("user:" + user, userPerMinute);
                if (!userBucket.tryConsume(clock.getAsLong())) {
                    return reject(exchange, userBucket);
                }
            }
            return chain.filter(exchange);
        });
    }

    private TokenBucket bucket(String key, int perMinute) {
        return buckets.get(key, k -> new TokenBucket(perMinute, clock.getAsLong()));
    }

    private static Mono<Void> reject(ServerWebExchange exchange, TokenBucket bucket) {
        return Problems.write(exchange.getResponse(), HttpStatus.TOO_MANY_REQUESTS, "Rate limit exceeded",
                Math.max(1, bucket.secondsUntilToken()));
    }

    private String clientIp(ServerWebExchange exchange) {
        if (trustForwardedFor) {
            String forwarded = exchange.getRequest().getHeaders().getFirst("X-Forwarded-For");
            if (forwarded != null && !forwarded.isBlank()) {
                return forwarded.split(",")[0].trim();
            }
        }
        InetSocketAddress remote = exchange.getRequest().getRemoteAddress();
        return remote == null || remote.getAddress() == null ? "unknown" : remote.getAddress().getHostAddress();
    }
}
