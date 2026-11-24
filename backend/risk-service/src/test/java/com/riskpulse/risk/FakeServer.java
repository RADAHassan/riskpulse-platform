package com.riskpulse.risk;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

/** Tiny in-process HTTP server used as a stand-in for ml-serving / audit / notification / transaction. */
final class FakeServer implements AutoCloseable {

    private final HttpServer server;
    final List<String> bodies = new CopyOnWriteArrayList<>();
    final AtomicInteger calls = new AtomicInteger();
    volatile int status = 200;
    volatile long delayMs = 0;
    volatile Supplier<String> response = () -> "{}";

    FakeServer(String path) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext(path, ex -> {
            calls.incrementAndGet();
            bodies.add(new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            if (delayMs > 0) {
                try {
                    Thread.sleep(delayMs);
                } catch (InterruptedException ignored) {
                    Thread.currentThread().interrupt();
                }
            }
            byte[] out = response.get().getBytes(StandardCharsets.UTF_8);
            ex.getResponseHeaders().add("Content-Type", "application/json");
            ex.sendResponseHeaders(status, out.length == 0 ? -1 : out.length);
            if (out.length > 0) {
                ex.getResponseBody().write(out);
            }
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
        delayMs = 0;
        response = () -> "{}";
    }

    static String ml(String decision, double probability, double uncertainty, String conformalSet, boolean humanReview) {
        return "{\"prediction\":" + (probability >= 0.5 ? 1 : 0) + ",\"probability\":" + probability
                + ",\"uncertainty\":" + uncertainty + ",\"decision\":\"" + decision + "\",\"conformal_set\":"
                + conformalSet + ",\"human_review\":" + humanReview + ",\"review_reason\":\"none\","
                + "\"model_version\":\"riskpulse-29d-v2.0-canonical\",\"registry_version\":\"7\",\"model_source\":\"mlflow\"}";
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
