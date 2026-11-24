package com.riskpulse.risk.service;

import com.riskpulse.risk.domain.ReviewCase;
import com.riskpulse.risk.domain.ReviewCaseRepository;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

/** Exposes {@code riskpulse_review_queue_size}: open human-review cases (cached 5 s to keep scrapes cheap). */
@Component
public class ReviewQueueMetrics {

    private static final long TTL_MS = 5_000;

    private final ReviewCaseRepository reviews;
    private final AtomicLong cached = new AtomicLong();
    private volatile long refreshedAt;

    public ReviewQueueMetrics(ReviewCaseRepository reviews, MeterRegistry registry) {
        this.reviews = reviews;
        Gauge.builder("riskpulse.review.queue.size", this, ReviewQueueMetrics::size)
                .description("Open cases waiting for a human decision").register(registry);
    }

    double size() {
        long now = System.currentTimeMillis();
        if (now - refreshedAt > TTL_MS) {
            try {
                cached.set(reviews.countByStatus(ReviewCase.Status.OPEN));
            } catch (RuntimeException e) {
                // keep the last known value when the database is briefly unavailable
            }
            refreshedAt = now;
        }
        return cached.get();
    }
}
