"""Generate docs/reports/riskpulse_backend_architecture.pdf (HTML + inline SVG diagrams -> Edge headless -> PDF).

    python scripts/gen_backend_report.py
"""

from __future__ import annotations

import subprocess
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_HTML = ROOT / "docs" / "reports" / "riskpulse_backend_architecture.html"
OUT_PDF = ROOT / "docs" / "reports" / "riskpulse_backend_architecture.pdf"

C = {"gw": "#dbeafe", "svc": "#dcfce7", "ml": "#fef3c7", "db": "#e5e7eb", "sec": "#fee2e2", "ui": "#ede9fe", "obs": "#cffafe"}


def box(x, y, w, h, title, lines=(), fill="#fff", bold=True):
    s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="#334155" stroke-width="1.2"/>'
    s += f'<text x="{x + w / 2}" y="{y + 16}" text-anchor="middle" font-weight="{"700" if bold else "400"}" font-size="12">{escape(title)}</text>'
    for i, line in enumerate(lines):
        s += f'<text x="{x + 8}" y="{y + 33 + i * 13}" font-size="10" fill="#334155">{escape(line)}</text>'
    return s


def arrow(x1, y1, x2, y2, label="", dashed=False, lx=0, ly=-4):
    dash = ' stroke-dasharray="5,4"' if dashed else ""
    s = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#475569" stroke-width="1.4"{dash} marker-end="url(#a)"/>'
    if label:
        s += f'<text x="{(x1 + x2) / 2 + lx}" y="{(y1 + y2) / 2 + ly}" text-anchor="middle" font-size="9.5" fill="#0f172a">{escape(label)}</text>'
    return s


def svg(w, h, body):
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Arial, sans-serif">'
            '<defs><marker id="a" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#475569"/></marker></defs>'
            f"{body}</svg>")


def component_diagram() -> str:
    b = box(10, 10, 130, 44, "React UI", ["nginx :8080, /api proxy"], C["ui"])
    b += box(190, 10, 170, 56, "API Gateway :8080", ["JWT RS256 validation", "rate limit IP/user, CORS, CSP"], C["gw"])
    b += arrow(140, 32, 190, 32, "HTTPS /api")
    b += box(30, 120, 130, 56, "auth-service :8081", ["login, refresh, JWKS", "lockout, BCrypt"], C["svc"])
    b += box(180, 120, 140, 56, "customer-service :8082", ["CRUD + BOLA"], C["svc"])
    b += box(340, 120, 150, 56, "transaction-service :8083", ["submit, simulator", "riskpulse_transactions"], C["svc"])
    b += box(510, 120, 130, 56, "risk-service :8084", ["decision policy", "review queue, R4J"], C["svc"])
    b += box(660, 120, 150, 56, "notification-svc :8085", ["per-customer scope"], C["svc"])
    b += box(830, 120, 130, 56, "audit-service :8086", ["append-only", "hash chain"], C["svc"])
    for x in (95, 250, 415, 575, 735, 895):
        b += arrow(275, 66, x, 120)
    b += arrow(415, 176, 510, 176 - 10, "REST + JWT", lx=0, ly=-6)
    b += box(500, 250, 170, 56, "ml-serving (FastAPI) :8000", ["predict, uncertainty, conformal", "X-Service-Key"], C["ml"])
    b += arrow(575, 176, 585, 250, "timeout / retry / CB", lx=60)
    b += box(720, 250, 150, 56, "MLflow :5000", ["registry riskpulse-fraud", "alias champion"], C["ml"])
    b += arrow(670, 278, 720, 278, "load champion")
    b += arrow(575, 176, 735, 176 + 0, "")
    b += box(30, 360, 930, 46, "PostgreSQL 17 — one database + one role per service (auth, customer, transaction, risk, notification, audit, mlflow)", [], C["db"])
    for x in (95, 250, 415, 575, 735, 895):
        b += arrow(x, 176, x, 360, dashed=True)
    b += box(10, 250, 440, 70, "Cross-cutting (riskpulse-common)", ["Resource-server security, ServiceKeyFilter (/internal/**), RFC 7807 errors,", "request-id, log masking, AuditClient, ServiceClients (JWT propagation)"], C["sec"])
    b += box(790, 330 - 10, 0, 0, "")
    b += box(10, 430, 950, 40, "Observability: Micrometer -> Prometheus -> Grafana / Alertmanager  (riskpulse_ml_*, riskpulse_transactions_total, riskpulse_review_queue_size)", [], C["obs"])
    return svg(980, 480, b)


def sequence_diagram() -> str:
    parts = ["Client", "Gateway", "transaction", "risk", "ml-serving", "audit", "notification"]
    xs = {p: 70 + i * 135 for i, p in enumerate(parts)}
    b = ""
    for p, x in xs.items():
        b += box(x - 50, 8, 100, 26, p, [], "#e0e7ff")
        b += f'<line x1="{x}" y1="34" x2="{x}" y2="500" stroke="#94a3b8" stroke-dasharray="3,4"/>'
    msgs = [
        ("Client", "Gateway", "POST /api/transactions + JWT", 62),
        ("Gateway", "Gateway", "validate JWT, rate limit, role gate", 84),
        ("Gateway", "transaction", "forward (JWT, X-Request-Id)", 106),
        ("transaction", "transaction", "owner check (BOLA) + persist PENDING", 128),
        ("transaction", "risk", "POST /internal/risk/assess (JWT + service key)", 152),
        ("risk", "ml-serving", "POST /predict (timeout 1.5 s, retry, circuit breaker)", 176),
        ("ml-serving", "risk", "probability, uncertainty, conformal set, decision", 200),
        ("risk", "risk", "DecisionPolicy: uncertain => never DECLINE; ML down => HUMAN_REVIEW", 226),
        ("risk", "risk", "save assessment (+ review case if HUMAN_REVIEW)", 250),
        ("risk", "audit", "RISK_DECISION (model version, probability)", 274),
        ("risk", "notification", "REVIEW_REQUIRED / TRANSACTION_DECLINED", 298),
        ("risk", "transaction", "decision", 322),
        ("transaction", "transaction", "status APPROVED | UNDER_REVIEW | DECLINED, counter", 346),
        ("transaction", "Client", "201 + decision", 372),
        ("Client", "risk", "analyst: POST /api/reviews/{id}/resolve (via gateway)", 410),
        ("risk", "audit", "REVIEW_RESOLVED", 434),
        ("risk", "transaction", "PUT /internal/transactions/{id}/decision", 458),
    ]
    for a, c, text, y in msgs:
        x1, x2 = xs[a], xs[c]
        if a == c:
            b += f'<path d="M{x1},{y} h28 v14 h-28" fill="none" stroke="#475569" marker-end="url(#a)"/>'
            b += f'<text x="{x1 + 34}" y="{y + 10}" font-size="9.5">{escape(text)}</text>'
        else:
            dashed = x2 < x1
            b += arrow(x1, y, x2, y, "", dashed)
            lx = (x1 + x2) / 2
            b += f'<text x="{lx}" y="{y - 4}" text-anchor="middle" font-size="9.5">{escape(text)}</text>'
    return svg(980, 510, b)


def decision_flow() -> str:
    b = box(10, 10, 200, 40, "ml-serving answered ?", [], C["gw"])
    b += box(300, 10, 260, 40, "NO -> HUMAN_REVIEW (fallback)", ["never APPROVE on failure"], C["sec"])
    b += arrow(210, 30, 300, 30, "no / timeout / circuit open")
    b += box(10, 90, 200, 40, "proposed = DECLINE ?", [], C["gw"])
    b += arrow(110, 50, 110, 90, "yes")
    b += box(300, 90, 300, 56, "uncertainty >= 0.25 OR conformal set != {FRAUD}", ["=> HUMAN_REVIEW (never auto-declined)"], C["ml"])
    b += arrow(210, 110, 300, 110, "yes")
    b += box(300, 170, 300, 40, "else DECLINE (p >= 0.80, singleton FRAUD)", [], C["sec"])
    b += arrow(110, 130, 110, 190, "")
    b += arrow(110, 190, 300, 190, "confident")
    b += box(10, 230, 200, 40, "proposed = HUMAN_REVIEW ?", [], C["gw"])
    b += arrow(110, 190, 110, 230, "no")
    b += box(300, 235, 300, 30, "=> HUMAN_REVIEW + review case", [], C["ml"])
    b += arrow(210, 250, 300, 250, "yes")
    b += box(10, 300, 200, 40, "router flag (top 0.5 % score) ?", [], C["gw"])
    b += arrow(110, 270, 110, 300, "no")
    b += box(300, 305, 300, 30, "yes => HUMAN_REVIEW", [], C["ml"])
    b += arrow(210, 320, 300, 320, "yes")
    b += box(10, 370, 200, 30, "APPROVE", [], C["svc"])
    b += arrow(110, 340, 110, 370, "no")
    return svg(640, 410, b)


def class_diagram() -> str:
    def cls(x, y, name, attrs, fill=C["svc"]):
        h = 22 + len(attrs) * 13 + 8
        s = box(x, y, 170, h, name, attrs, fill)
        s += f'<line x1="{x}" y1="{y + 22}" x2="{x + 170}" y2="{y + 22}" stroke="#334155"/>'
        return s, h

    b = ""
    items = [
        (10, 10, "UserAccount (auth)", ["id: UUID", "username (unique)", "passwordHash BCrypt", "role: ADMIN|ANALYST|CUSTOMER", "customerId?", "failedAttempts, lockedUntil"]),
        (200, 10, "RefreshToken (auth)", ["id, userId", "tokenHash SHA-256", "expiresAt, revokedAt"]),
        (390, 10, "Customer", ["id: UUID", "firstName, lastName", "email (unique)", "country, segment"]),
        (580, 10, "Transaction", ["id, customerId", "amount, currency", "features double[28]", "status, decision", "probability, uncertainty", "modelVersion, simulated"]),
        (10, 190, "RiskAssessment", ["id, transactionId (unique)", "probability, uncertainty", "decision, reason, fallback", "modelVersion, registryVersion", "conformalSet"]),
        (200, 190, "ReviewCase", ["id, assessmentId", "transactionId (unique)", "status OPEN|APPROVED|REJECTED", "resolvedBy, note"]),
        (390, 190, "Notification", ["id, type, severity", "subject, message", "transactionId?, customerId?", "read"]),
        (580, 190, "AuditRecord", ["seq, id, occurredAt", "actor, action, resource", "decision, modelVersion", "prevHash, hash (SHA-256)", "DB trigger: no UPDATE/DELETE"]),
    ]
    for x, y, n, a in items:
        s, _ = cls(x, y, n, a)
        b += s
    b += arrow(95, 128, 95, 190, "", True)
    b += arrow(200, 215, 180, 215, "")
    b += arrow(285, 190, 285, 170, "")
    b += arrow(665, 128, 665, 190, "", True)
    b += arrow(180, 60, 200, 60, "1..*")
    b += arrow(95, 270, 200, 270, "1 - 0..1")
    return svg(780, 330, b)


def security_diagram() -> str:
    rows = [
        ("Edge (gateway)", "JWT RS256 + JWKS, role gates, rate limit IP/user/login, CSP/HSTS/X-Frame, CORS allow-list, 1 MiB limit, X-Service-Key stripped, /internal blocked"),
        ("Every service", "Resource server (re-validates the JWT), method security, ownership check (BOLA), RFC 7807 without stack trace, log masking"),
        ("Service-to-service", "Propagated JWT + X-Service-Key on /internal/**, Resilience4j timeout/retry/circuit breaker, fallback = HUMAN_REVIEW"),
        ("Auth", "15 min access token, rotating refresh token with reuse detection, lockout after N failures, BCrypt, key rotation via JWKS (previous key)"),
        ("Data", "One DB + one role per service, Flyway, audit table append-only (trigger) + SHA-256 hash chain verified by /verify"),
        ("ml-serving", "Service key, strict Pydantic schema (28 finite features), batch/body limits, non-root read-only container"),
    ]
    b = ""
    for i, (k, v) in enumerate(rows):
        y = 10 + i * 58
        b += box(10, y, 150, 46, k, [], C["sec"])
        words, line, lines = v.split(), "", []
        for w in words:
            if len(line) + len(w) > 105:
                lines.append(line)
                line = ""
            line += w + " "
        lines.append(line)
        b += box(170, y, 790, 46, "", lines[:3], "#fff")
    return svg(980, 370, b)


HTML = """<!doctype html><html><head><meta charset="utf-8"><title>RiskPulse backend architecture</title>
<style>
@page { size: A4 landscape; margin: 12mm; }
body { font-family: 'Segoe UI', Arial, sans-serif; color:#0f172a; font-size: 12px; }
h1 { font-size: 24px; margin:0 0 4px } h2 { font-size: 16px; border-bottom: 2px solid #1f5fbf; padding-bottom:3px; margin:0 0 8px }
.page { page-break-after: always; } .muted { color:#64748b }
table { border-collapse: collapse; width: 100%; font-size: 11px } th,td { border:1px solid #cbd5e1; padding:3px 6px; text-align:left } th { background:#eff6ff }
</style></head><body>
<div class="page"><h1>RiskPulse — Backend architecture</h1>
<p class="muted">Spring Boot 4.2 / Java 21 microservices, verified with <code>mvn -B verify</code> (all modules green).</p>
<table><tr><th>Module</th><th>Port</th><th>Responsibility</th><th>Tests (unit / WebMvc / Testcontainers IT)</th></tr>
<tr><td>riskpulse-common</td><td>-</td><td>Security, errors, logging, clients (library)</td><td>14</td></tr>
<tr><td>api-gateway</td><td>8080</td><td>Spring Cloud Gateway: JWT, rate limiting, headers, routing, OpenAPI</td><td>18 (WebTestClient)</td></tr>
<tr><td>auth-service</td><td>8081</td><td>Login, refresh rotation, JWKS, users, lockout</td><td>3 + 10 IT</td></tr>
<tr><td>customer-service</td><td>8082</td><td>Customer CRUD with ownership rules</td><td>4 WebMvc + 6 IT</td></tr>
<tr><td>transaction-service</td><td>8083</td><td>Submit, simulator (admin), decisions, business metrics</td><td>3 + 8 IT</td></tr>
<tr><td>risk-service</td><td>8084</td><td>ml-serving client (Resilience4j), decision policy, human review queue</td><td>15 + 10 IT</td></tr>
<tr><td>notification-service</td><td>8085</td><td>Notifications scoped per customer</td><td>4 IT</td></tr>
<tr><td>audit-service</td><td>8086</td><td>Append-only hash-chained audit log</td><td>3 + 7 IT</td></tr></table>
<p><b>Around it:</b> ml-serving (FastAPI, 25 tests, 92 % coverage), MLflow pipeline (train/import &rarr; evaluate &rarr; statistical gates &rarr; registry &rarr; deploy, executed end to end), React UI (24 tests).</p>
<h2>1. Component diagram</h2>__COMPONENT__</div>
<div class="page"><h2>2. Sequence — submitting a transaction and human review</h2>__SEQ__</div>
<div class="page"><h2>3. Decision policy (risk-service) — an uncertain prediction is never auto-declined</h2>__FLOW__
<p class="muted">Implemented in <code>DecisionPolicy</code> (exhaustively unit-tested) and mirrored in ml-serving; failures of ml-serving never lead to APPROVE.</p></div>
<div class="page"><h2>4. Domain model (one database per service)</h2>__CLASS__
<p class="muted">No cross-database foreign keys: services reference each other by id only (customerId, transactionId).</p></div>
<div class="page"><h2>5. Security layers (OWASP API Top 10)</h2>__SEC__</div>
</body></html>"""


def main() -> None:
    html = (HTML.replace("__COMPONENT__", component_diagram()).replace("__SEQ__", sequence_diagram())
            .replace("__FLOW__", decision_flow()).replace("__CLASS__", class_diagram()).replace("__SEC__", security_diagram()))
    OUT_HTML.write_text(html, encoding="utf-8")
    edge = next((p for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                             r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                             r"C:\Program Files\Google\Chrome\Application\chrome.exe") if Path(p).exists()), None)
    if not edge:
        raise SystemExit("Edge/Chrome not found: open the HTML and print it to PDF")
    subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={OUT_PDF}", OUT_HTML.as_uri()], check=True, timeout=120)
    OUT_HTML.unlink()
    print(f"wrote {OUT_PDF}")


if __name__ == "__main__":
    main()
