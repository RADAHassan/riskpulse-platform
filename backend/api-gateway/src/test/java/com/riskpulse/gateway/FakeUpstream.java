package com.riskpulse.gateway;

import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

/** Captures what the gateway forwards to a downstream service. */
final class FakeUpstream implements AutoCloseable {

    private final HttpServer server;
    final AtomicReference<Headers> lastHeaders = new AtomicReference<>();
    final AtomicReference<String> lastPath = new AtomicReference<>();
    final AtomicInteger calls = new AtomicInteger();

    FakeUpstream() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", ex -> {
            calls.incrementAndGet();
            lastHeaders.set(ex.getRequestHeaders());
            lastPath.set(ex.getRequestURI().getPath());
            ex.getRequestBody().readAllBytes();
            byte[] out = "{\"ok\":true}".getBytes(StandardCharsets.UTF_8);
            ex.getResponseHeaders().add("Content-Type", "application/json");
            ex.getResponseHeaders().add("Server", "Apache-Coyote/leaky-1.2.3");
            ex.sendResponseHeaders(200, out.length);
            ex.getResponseBody().write(out);
            ex.close();
        });
        server.start();
    }

    String url() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    String header(String name) {
        Headers h = lastHeaders.get();
        return h == null ? null : h.getFirst(name);
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
