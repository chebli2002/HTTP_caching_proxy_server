"""
Web dashboard for monitoring the proxy server.
Team attribution:
- Nabil: threaded socket accept loop for UI clients
- Chebli: integration with proxy stats and runtime wiring
- John: UI log display and monitoring endpoints
"""

import socket
import threading
import time
import json

from config import BUFFER_SIZE, UI_HOST, UI_PORT
from logger import log_message, read_recent_logs
from proxy_handler import get_proxy_stats, get_recent_requests


def _http_response(status_line, body, content_type="text/html"):
    body_bytes = body.encode("utf-8", errors="replace")
    headers = (
        f"{status_line}\r\n"
        f"Content-Type: {content_type}; charset=utf-8\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    return headers.encode("utf-8") + body_bytes


def _stats_text():
    stats = get_proxy_stats()
    uptime_seconds = int(time.time() - START_TIME)
    return (
        f"total_requests={stats['total_requests']}\n"
        f"cache_hits={stats['cache_hits']}\n"
        f"blocked_requests={stats['blocked_requests']}\n"
        f"error_requests={stats['error_requests']}\n"
        f"uptime_seconds={uptime_seconds}\n"
    )


def _logs_text():
    lines = read_recent_logs(limit=80)
    return "".join(lines) if lines else "No logs yet.\n"


def _dashboard_html():
    return """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>HTTP Proxy Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; background: #0b1220; color: #e2e8f0; margin: 0; padding: 24px; }
    .layout { display: grid; grid-template-columns: 1fr; gap: 16px; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(190px, 1fr)); gap: 12px; }
    .card { background: #162338; border-radius: 12px; padding: 14px; border: 1px solid #2a3b5a; }
    .panel { background: #101a2d; border-radius: 12px; padding: 14px; border: 1px solid #2a3b5a; }
    h1, h2, h3 { margin: 0 0 12px 0; }
    .value { font-size: 26px; font-weight: bold; margin-top: 6px; }
    .label { color: #9fb0cc; font-size: 13px; }
    .sub { color: #8ea0be; font-size: 12px; margin-top: 6px; }
    pre { background: #040914; padding: 12px; border-radius: 8px; height: 210px; overflow: auto; border: 1px solid #243353; }
    .table-wrap { overflow: auto; max-height: 300px; border-radius: 8px; border: 1px solid #2a3b5a; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 860px; }
    th, td { padding: 8px; border-bottom: 1px solid #273955; text-align: left; }
    th { position: sticky; top: 0; background: #1a2a44; color: #c8d6ec; }
    .ok { color: #67e8a5; }
    .error { color: #fca5a5; }
  </style>
</head>
<body>
  <h1>Modular HTTP Proxy Dashboard</h1>
  <div class="layout">
    <div class="grid">
      <div class="card"><div class="label">Total Requests</div><div id="total_requests" class="value">0</div></div>
      <div class="card"><div class="label">HTTP Requests</div><div id="http_count" class="value">0</div></div>
      <div class="card"><div class="label">HTTPS Requests</div><div id="https_count" class="value">0</div></div>
      <div class="card"><div class="label">Cache Hits</div><div id="cache_hits" class="value">0</div></div>
      <div class="card"><div class="label">Blocked Requests</div><div id="blocked_requests" class="value">0</div></div>
      <div class="card"><div class="label">Error Requests</div><div id="error_requests" class="value">0</div></div>
      <div class="card"><div class="label">Uptime (seconds)</div><div id="uptime_seconds" class="value">0</div></div>
      <div class="card"><div class="label">Last Status</div><div id="last_status" class="value">-</div><div id="last_status_meta" class="sub">waiting for traffic</div></div>
      <div class="card"><div class="label">Last URL</div><div id="last_url" class="value" style="font-size:14px; word-break: break-all;">-</div></div>
    </div>

    <div class="panel">
      <h3>HTTP Requests</h3>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Time</th><th>Client</th><th>Method</th><th>URL</th><th>Status</th><th>Error</th></tr></thead>
          <tbody id="http_rows"></tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <h3>HTTPS Requests</h3>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Time</th><th>Client</th><th>Method</th><th>URL</th><th>Status</th><th>Error</th></tr></thead>
          <tbody id="https_rows"></tbody>
        </table>
      </div>
    </div>

    <div class="panel">
      <h3>Recent Raw Logs</h3>
      <pre id="logs">Loading logs...</pre>
    </div>
  </div>
  <script>
    function parseKeyValues(text) {
      const values = {};
      text.trim().split("\\n").forEach((line) => {
        const idx = line.indexOf("=");
        if (idx > 0) {
          const key = line.slice(0, idx);
          const value = line.slice(idx + 1);
          values[key] = value;
        }
      });
      return values;
    }

    async function refresh() {
      try {
        const statsRes = await fetch("/api/stats");
        const statsTxt = await statsRes.text();
        const stats = parseKeyValues(statsTxt);
        ["total_requests", "cache_hits", "blocked_requests", "error_requests", "uptime_seconds"].forEach((key) => {
          const el = document.getElementById(key);
          if (el) el.textContent = stats[key] || "0";
        });
      } catch (_) {}

      try {
        const requestsRes = await fetch("/api/requests");
        const requests = await requestsRes.json();
        const httpRows = document.getElementById("http_rows");
        const httpsRows = document.getElementById("https_rows");
        httpRows.innerHTML = "";
        httpsRows.innerHTML = "";

        let httpCount = 0;
        let httpsCount = 0;

        requests.forEach((entry) => {
          const row = document.createElement("tr");
          const statusClass = Number(entry.status) >= 400 ? "error" : "ok";
          row.innerHTML = `
            <td>${entry.response_time || "-"}</td>
            <td>${entry.client_ip}:${entry.client_port}</td>
            <td>${entry.method}</td>
            <td>${entry.url}</td>
            <td class="${statusClass}">${entry.status}</td>
            <td>${entry.error || "-"}</td>
          `;
          if (entry.protocol === "HTTPS") {
            httpsCount += 1;
            httpsRows.appendChild(row);
          } else {
            httpCount += 1;
            httpRows.appendChild(row);
          }
        });

        document.getElementById("http_count").textContent = String(httpCount);
        document.getElementById("https_count").textContent = String(httpsCount);

        if (requests.length > 0) {
          const last = requests[requests.length - 1];
          document.getElementById("last_status").textContent = last.status || "-";
          document.getElementById("last_status_meta").textContent = `${last.protocol || "-"} ${last.method || "-"}`;
          document.getElementById("last_url").textContent = last.url || "-";
        }
      } catch (_) {}

      try {
        const logsRes = await fetch("/api/logs");
        const logsTxt = await logsRes.text();
        document.getElementById("logs").textContent = logsTxt;
      } catch (_) {}
    }

    refresh();
    setInterval(refresh, 2000);
  </script>
</body>
</html>
"""


def _handle_ui_client(client_socket, client_address):
    try:
        request_data = client_socket.recv(BUFFER_SIZE)
        if not request_data:
            return

        request_text = request_data.decode("utf-8", errors="replace")
        first_line = request_text.split("\r\n")[0]
        parts = first_line.split(" ")
        if len(parts) < 2:
            client_socket.sendall(_http_response("HTTP/1.1 400 Bad Request", "Bad Request", "text/plain"))
            return

        method = parts[0].upper()
        path = parts[1]

        if method != "GET":
            client_socket.sendall(_http_response("HTTP/1.1 405 Method Not Allowed", "Only GET allowed", "text/plain"))
            return

        if path == "/" or path == "/index.html":
            client_socket.sendall(_http_response("HTTP/1.1 200 OK", _dashboard_html(), "text/html"))
            return

        if path == "/api/stats":
            client_socket.sendall(_http_response("HTTP/1.1 200 OK", _stats_text(), "text/plain"))
            return

        if path == "/api/logs":
            client_socket.sendall(_http_response("HTTP/1.1 200 OK", _logs_text(), "text/plain"))
            return

        if path == "/api/requests":
            body = json.dumps(get_recent_requests(limit=120))
            client_socket.sendall(_http_response("HTTP/1.1 200 OK", body, "application/json"))
            return

        client_socket.sendall(_http_response("HTTP/1.1 404 Not Found", "Not Found", "text/plain"))
    except Exception as error:
        log_message(f"UI client error from {client_address}: {error}", "ERROR")
    finally:
        try:
            client_socket.close()
        except OSError:
            pass


def start_ui_server(host=UI_HOST, port=UI_PORT):
    """Start the web dashboard socket server."""
    ui_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ui_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ui_socket.bind((host, port))
    ui_socket.listen(5)
    log_message(f"Dashboard started on http://{host}:{port}")

    try:
        while True:
            client_socket, client_address = ui_socket.accept()
            client_thread = threading.Thread(
                target=_handle_ui_client,
                args=(client_socket, client_address),
                daemon=True,
            )
            client_thread.start()
    finally:
        ui_socket.close()


START_TIME = time.time()
