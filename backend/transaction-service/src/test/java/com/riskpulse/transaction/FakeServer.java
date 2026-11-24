package com.riskpulse.transaction;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

/** In-process stand-in for risk-service / audit-service. */
final class FakeServer implements AutoCloseable {

    private final HttpServer server;
    final List<String> bodies = new CopyOnWriteArrayList<>();
    final AtomicInteger calls = new AtomicInteger();
    volatile int status = 200;
    volatile Supplier<String> response = () -> "{}";

    FakeServer(String path) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext(path, ex -> {
            calls.incrementAndGet();
            bodies.add(new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] out = response.get().getBytes(StandardCharsets.UTF_8);
            ex.getResponseHeaders().add("Content-Type", "application/json");
            ex.sendResponseHeaders(status, out.length);
            ex.getResponseBody().write(out);
            ex.close();
        });
        server.start();
    }

    String url() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    void reset() {
        bodies.clear();
        calls.set(0);
        status = 200;
        response = () -> "{}";
    }

    static String risk(String decision, String reason, double p, double u, boolean fallback) {
        return "{\"decision\":\"" + decision + "\",\"reason\":\"" + reason + "\",\"probability\":" + p
                + ",\"uncertainty\":" + u + ",\"modelVersion\":\"riskpulse-29d-v2.0-canonical\",\"fallback\":"
                + fallback + "}";
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
