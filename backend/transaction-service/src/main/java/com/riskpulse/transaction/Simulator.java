package com.riskpulse.transaction;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

/**
 * Replays demo transactions (CSV: {@code amount, v1..v28, is_fraud}). Source: the ULB test tail when
 * {@code ml/data/creditcard.csv} was available at generation time, otherwise synthetic payloads
 * (see scripts/generate_demo_transactions.py).
 */
@Component
public class Simulator {

    public record Sample(BigDecimal amount, List<Double> features, boolean fraud) {
    }

    private static final Logger LOG = LoggerFactory.getLogger(Simulator.class);
    private static final int N_FEATURES = 28;
    private static final List<UUID> DEMO_CUSTOMERS = demoCustomers();

    private final List<Sample> legit = new ArrayList<>();
    private final List<Sample> fraud = new ArrayList<>();

    public Simulator(@Value("${riskpulse.simulator.data-path:}") String dataPath) throws IOException {
        try (InputStream in = dataPath == null || dataPath.isBlank()
                ? new ClassPathResource("demo_transactions.csv").getInputStream()
                : Files.newInputStream(Path.of(dataPath))) {
            load(in);
        }
        LOG.info("Simulator loaded {} legit and {} fraud-labelled payloads", legit.size(), fraud.size());
    }

    void load(InputStream in) throws IOException {
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            String line = reader.readLine(); // header
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }
                String[] cols = line.split(",");
                if (cols.length != N_FEATURES + 2) {
                    continue;
                }
                List<Double> features = new ArrayList<>(N_FEATURES);
                for (int i = 1; i <= N_FEATURES; i++) {
                    features.add(Double.parseDouble(cols[i]));
                }
                Sample s = new Sample(new BigDecimal(cols[0]), features, "1".equals(cols[N_FEATURES + 1].trim()));
                (s.fraud() ? fraud : legit).add(s);
            }
        }
        if (legit.isEmpty() && fraud.isEmpty()) {
            throw new IllegalStateException("No demo transactions available for the simulator");
        }
    }

    /** @param fraudRatio share of fraud-labelled payloads in [0,1]; {@code null} keeps the dataset prevalence. */
    public List<Sample> draw(int count, Double fraudRatio) {
        double ratio = fraudRatio != null ? fraudRatio
                : (double) fraud.size() / Math.max(1, fraud.size() + legit.size());
        List<Sample> out = new ArrayList<>(count);
        ThreadLocalRandom rnd = ThreadLocalRandom.current();
        for (int i = 0; i < count; i++) {
            boolean pickFraud = !fraud.isEmpty() && (legit.isEmpty() || rnd.nextDouble() < ratio);
            List<Sample> pool = pickFraud ? fraud : legit;
            out.add(pool.get(rnd.nextInt(pool.size())));
        }
        return out;
    }

    public UUID randomCustomer() {
        return DEMO_CUSTOMERS.get(ThreadLocalRandom.current().nextInt(DEMO_CUSTOMERS.size()));
    }

    private static List<UUID> demoCustomers() {
        List<UUID> ids = new ArrayList<>();
        for (int i = 1; i <= 20; i++) {
            ids.add(UUID.nameUUIDFromBytes(("riskpulse-demo-customer-" + i).getBytes(StandardCharsets.UTF_8)));
        }
        return List.copyOf(ids);
    }
}
