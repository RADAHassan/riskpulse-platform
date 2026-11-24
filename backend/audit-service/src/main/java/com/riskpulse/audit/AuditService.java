package com.riskpulse.audit;

import com.riskpulse.audit.AuditController.AuditEventRequest;
import jakarta.persistence.EntityManager;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Hash-chained append-only log: {@code hash = SHA-256(prev_hash | fields...)}. Any modification or removal of a
 * past row breaks the chain and is detected by {@link #verify()}. Appends are serialised by a transaction-level
 * advisory lock so that concurrent writers never fork the chain.
 */
@Service
public class AuditService {

    static final String GENESIS = "0".repeat(64);
    private static final long CHAIN_LOCK = 7_001L;
    private static final int MAX_DETAIL_VALUE = 500;

    public record Verification(boolean valid, long checked, Long firstBrokenSeq, String reason) {
    }

    private final AuditRepository repository;
    private final EntityManager entityManager;

    public AuditService(AuditRepository repository, EntityManager entityManager) {
        this.repository = repository;
        this.entityManager = entityManager;
    }

    @Transactional
    public AuditRecord append(AuditEventRequest request) {
        entityManager.createNativeQuery("select pg_advisory_xact_lock(:k)").setParameter("k", CHAIN_LOCK).getSingleResult();
        String prev = repository.findFirstByOrderBySeqDesc().map(AuditRecord::getHash).orElse(GENESIS);
        UUID id = UUID.randomUUID();
        Instant at = Instant.now().truncatedTo(ChronoUnit.MICROS);
        String details = canonicalDetails(request.details());
        String hash = computeHash(prev, id, at, request.actor(), request.actorRole(), request.action(),
                request.resourceType(), request.resourceId(), request.decision(), request.modelVersion(), details);
        AuditRecord record = new AuditRecord(id, at, request.actor(), request.actorRole(), request.action(),
                request.resourceType(), request.resourceId(), request.decision(), request.modelVersion(), details, prev,
                hash);
        entityManager.persist(record); // persist (not merge): the row is new and `seq` is database generated
        entityManager.flush();
        return record;
    }

    @Transactional(readOnly = true)
    public Verification verify() {
        String expectedPrev = GENESIS;
        long checked = 0;
        long afterSeq = 0;
        while (true) {
            List<AuditRecord> chunk = repository.chunkAfter(afterSeq, PageRequest.of(0, 500));
            if (chunk.isEmpty()) {
                return new Verification(true, checked, null, null);
            }
            for (AuditRecord r : chunk) {
                if (!r.getPrevHash().equals(expectedPrev)) {
                    return new Verification(false, checked, r.getSeq(), "previous hash does not match (row removed or reordered)");
                }
                String recomputed = computeHash(r.getPrevHash(), r.getId(), r.getOccurredAt(), r.getActor(),
                        r.getActorRole(), r.getAction(), r.getResourceType(), r.getResourceId(), r.getDecision(),
                        r.getModelVersion(), r.getDetails());
                if (!recomputed.equals(r.getHash())) {
                    return new Verification(false, checked, r.getSeq(), "content hash mismatch (row modified)");
                }
                expectedPrev = r.getHash();
                afterSeq = r.getSeq();
                checked++;
            }
            entityManager.clear();
        }
    }

    static String computeHash(String prev, UUID id, Instant at, String actor, String role, String action, String type,
                              String resourceId, String decision, String modelVersion, String details) {
        String material = String.join("|", prev, id.toString(), at.toString(), n(actor), n(role), n(action), n(type),
                n(resourceId), n(decision), n(modelVersion), n(details));
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(material.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    /** Deterministic JSON (sorted keys, string values, bounded length) so the hash is reproducible. */
    static String canonicalDetails(Map<String, Object> details) {
        if (details == null || details.isEmpty()) {
            return "{}";
        }
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> e : new TreeMap<>(details).entrySet()) {
            if (!first) {
                sb.append(',');
            }
            first = false;
            String value = String.valueOf(e.getValue());
            if (value.length() > MAX_DETAIL_VALUE) {
                value = value.substring(0, MAX_DETAIL_VALUE);
            }
            sb.append('"').append(escape(e.getKey())).append("\":\"").append(escape(value)).append('"');
        }
        return sb.append('}').toString();
    }

    private static String escape(String s) {
        StringBuilder sb = new StringBuilder();
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
                }
            }
        }
        return sb.toString();
    }

    private static String n(String s) {
        return s == null ? "" : s;
    }
}
