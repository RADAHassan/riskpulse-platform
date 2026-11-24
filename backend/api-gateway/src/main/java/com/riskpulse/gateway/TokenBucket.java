package com.riskpulse.gateway;

/** Minimal thread-safe token bucket: {@code perMinute} tokens, refilled continuously. */
final class TokenBucket {

    private final double capacity;
    private final double refillPerNano;
    private double tokens;
    private long lastRefill;

    TokenBucket(int perMinute, long nowNanos) {
        this.capacity = perMinute;
        this.refillPerNano = perMinute / 60_000_000_000.0;
        this.tokens = perMinute;
        this.lastRefill = nowNanos;
    }

    synchronized boolean tryConsume(long nowNanos) {
        tokens = Math.min(capacity, tokens + (nowNanos - lastRefill) * refillPerNano);
        lastRefill = nowNanos;
        if (tokens >= 1.0) {
            tokens -= 1.0;
            return true;
        }
        return false;
    }

    /** Seconds until one token is available (for Retry-After). */
    synchronized long secondsUntilToken() {
        double missing = 1.0 - tokens;
        return missing <= 0 ? 0 : (long) Math.ceil(missing / (refillPerNano * 1_000_000_000.0));
    }
}
