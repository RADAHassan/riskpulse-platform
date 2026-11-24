package com.riskpulse.common.security;

import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

/** Minimal RFC 7807 writer for filters / entry points (no stack trace, no reflected input). */
final class ProblemJson {

    private ProblemJson() {
    }

    static void write(HttpServletResponse response, int status, String title, String detail) throws IOException {
        response.setStatus(status);
        response.setContentType("application/problem+json");
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write("{\"type\":\"about:blank\",\"title\":\"" + escape(title) + "\",\"status\":" + status
                + ",\"detail\":\"" + escape(detail) + "\"}");
    }

    private static String escape(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", " ").replace("\r", " ");
    }
}
