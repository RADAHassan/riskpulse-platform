package com.riskpulse.common.logging;

import java.util.UUID;

/** Helpers to keep personal data and secrets out of logs and audit details. */
public final class Masking {

    private Masking() {
    }

    /** {@code alice@example.com} becomes {@code a***@example.com}. */
    public static String email(String email) {
        if (email == null || email.isBlank()) {
            return "";
        }
        int at = email.indexOf('@');
        if (at <= 0) {
            return "***";
        }
        return email.charAt(0) + "***" + email.substring(at);
    }

    /** Keeps the first 8 characters of an identifier so that log lines stay correlatable. */
    public static String id(UUID id) {
        return id == null ? "" : id.toString().substring(0, 8) + "…";
    }

    public static String secret(String ignored) {
        return "[REDACTED]";
    }

    /** Strips CR/LF to prevent log forging with user-controlled values. */
    public static String sanitize(String value) {
        return value == null ? "" : value.replaceAll("[\\r\\n\\t]", "_");
    }
}
