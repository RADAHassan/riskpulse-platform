package com.riskpulse.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class TokenBucketTest {

    private static final long SECOND = 1_000_000_000L;

    @Test
    void allowsTheBurstThenBlocks() {
        TokenBucket bucket = new TokenBucket(3, 0);
        assertThat(bucket.tryConsume(0)).isTrue();
        assertThat(bucket.tryConsume(0)).isTrue();
        assertThat(bucket.tryConsume(0)).isTrue();
        assertThat(bucket.tryConsume(0)).isFalse();
        assertThat(bucket.secondsUntilToken()).isPositive();
    }

    @Test
    void refillsOverTime() {
        TokenBucket bucket = new TokenBucket(60, 0); // 1 token per second
        for (int i = 0; i < 60; i++) {
            assertThat(bucket.tryConsume(0)).isTrue();
        }
        assertThat(bucket.tryConsume(0)).isFalse();
        assertThat(bucket.tryConsume(SECOND / 2)).isFalse();
        assertThat(bucket.tryConsume(2 * SECOND)).isTrue();
    }

    @Test
    void neverExceedsCapacity() {
        TokenBucket bucket = new TokenBucket(2, 0);
        assertThat(bucket.tryConsume(1_000 * SECOND)).isTrue();
        assertThat(bucket.tryConsume(1_000 * SECOND)).isTrue();
        assertThat(bucket.tryConsume(1_000 * SECOND)).isFalse();
    }
}
