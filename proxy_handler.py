"""
Proxy request/response handling module.
Team attribution:
- Chebli: proxy forwarding and cache flow
- Nabil: client socket lifecycle support
- John: logging + filtering integration
"""

import socket
import ssl
import threading
from datetime import datetime
from select import select

from cache import SimpleCache
from config import (
    BUFFER_SIZE,
    CACHE_ENABLED,
    HTTPS_CERT_FILE,
    HTTPS_KEY_FILE,
    HTTPS_MITM_ENABLED,
    SOCKET_TIMEOUT,
)
from filter import is_request_allowed
from logger import log_message, log_request, log_request_details
from parser import parse_http_request
from utils import create_error_response


shared_cache = SimpleCache()
stats_lock = threading.Lock()
proxy_stats = {
    "total_requests": 0,
    "cache_hits": 0,
    "blocked_requests": 0,
    "error_requests": 0,
}
request_history = []
MAX_REQUEST_HISTORY = 300
server_ssl_context = None


def _increment_stat(name):
    with stats_lock:
        proxy_stats[name] += 1


def get_proxy_stats():
    """Return a copy of current proxy stats for dashboard usage."""
    with stats_lock:
        return {
            "total_requests": proxy_stats["total_requests"],
            "cache_hits": proxy_stats["cache_hits"],
            "blocked_requests": proxy_stats["blocked_requests"],
            "error_requests": proxy_stats["error_requests"],
        }


def _record_request(entry):
    """Store recent request details for dashboard display."""
    with stats_lock:
        request_history.append(entry)
        if len(request_history) > MAX_REQUEST_HISTORY:
            del request_history[0 : len(request_history) - MAX_REQUEST_HISTORY]


def get_recent_requests(limit=100):
    """Return latest request entries for admin dashboard."""
    with stats_lock:
        if limit <= 0:
            return []
        return list(request_history[-limit:])


def _extract_status_code(response_data):
    """Extract status code from HTTP response bytes."""
    try:
        first_line = response_data.split(b"\r\n", 1)[0].decode("utf-8", errors="replace")
        parts = first_line.split(" ")
        if len(parts) >= 2:
            return parts[1]
    except Exception:
        pass
    return "000"


def _build_origin_request(request_data, host):
    """
    Convert proxy-form request into origin-form request for target server.
    Example: GET http://example.com/path HTTP/1.1 -> GET /path HTTP/1.1
    """
    head, separator, body = request_data.partition(b"\r\n\r\n")
    if not separator:
        return request_data

    try:
        head_text = head.decode("iso-8859-1", errors="replace")
    except Exception:
        return request_data

    lines = head_text.split("\r\n")
    if not lines or not lines[0]:
        return request_data

    request_line_parts = lines[0].split(" ", 2)
    if len(request_line_parts) != 3:
        return request_data

    method, target, version = request_line_parts

    # Proxy clients often send absolute-form URL. Origin servers expect path.
    path = target
    if target.startswith("http://"):
        no_scheme = target[7:]
        slash_index = no_scheme.find("/")
        path = "/" if slash_index == -1 else no_scheme[slash_index:]
    elif target.startswith("https://"):
        no_scheme = target[8:]
        slash_index = no_scheme.find("/")
        path = "/" if slash_index == -1 else no_scheme[slash_index:]

    new_first_line = f"{method} {path} {version}"

    new_headers = []
    has_host = False
    for line in lines[1:]:
        lowered = line.lower()
        if lowered.startswith("proxy-connection:"):
            continue
        if lowered.startswith("connection:"):
            continue
        if lowered.startswith("host:"):
            has_host = True
        new_headers.append(line)

    if not has_host:
        new_headers.append(f"Host: {host}")

    # Force close to avoid hanging reads with keep-alive.
    new_headers.append("Connection: close")

    new_head_text = "\r\n".join([new_first_line] + new_headers) + "\r\n\r\n"
    return new_head_text.encode("iso-8859-1", errors="replace") + body


def _forward_request(host, port, request_data):
    """Forward request to origin and return full response bytes."""
    origin_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    origin_socket.settimeout(SOCKET_TIMEOUT)
    try:
        origin_socket.connect((host, port))
        origin_request = _build_origin_request(request_data, host)
        origin_socket.sendall(origin_request)
        response_data = b""
        while True:
            try:
                chunk = origin_socket.recv(BUFFER_SIZE)
            except socket.timeout:
                # If any data already arrived, return it instead of failing.
                if response_data:
                    break
                raise
            if not chunk:
                break
            response_data += chunk
        return response_data
    finally:
        origin_socket.close()


def _get_server_ssl_context():
    """Create TLS server context used to decrypt client HTTPS traffic."""
    global server_ssl_context
    if server_ssl_context is None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=HTTPS_CERT_FILE, keyfile=HTTPS_KEY_FILE)
        server_ssl_context = context
    return server_ssl_context


def _extract_https_path_from_request(data):
    """Best-effort extraction of HTTPS request path for logs/filters."""
    try:
        first_line = data.decode("iso-8859-1", errors="replace").split("\r\n", 1)[0]
        parts = first_line.split(" ")
        if len(parts) >= 2 and parts[1].startswith("/"):
            return parts[1], first_line
        return "/", first_line
    except Exception:
        return "/", "-"


def _mitm_https_tunnel(client_socket, host, port):
    """
    MITM mode for HTTPS:
    1) ACK CONNECT
    2) TLS handshake with client (server-side cert)
    3) TLS handshake with origin (client-side)
    4) Relay decrypted data in both directions and inspect request line
    """
    if not HTTPS_MITM_ENABLED:
        raise RuntimeError("https_mitm_disabled")

    client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

    tls_server_context = _get_server_ssl_context()
    tls_client_context = ssl.create_default_context()
    client_tls = None
    origin_tcp = None
    origin_tls = None

    try:
        client_tls = tls_server_context.wrap_socket(client_socket, server_side=True)
        origin_tcp = socket.create_connection((host, port), timeout=SOCKET_TIMEOUT)
        origin_tls = tls_client_context.wrap_socket(origin_tcp, server_hostname=host)

        client_tls.settimeout(SOCKET_TIMEOUT)
        origin_tls.settimeout(SOCKET_TIMEOUT)
        idle_rounds = 0

        while True:
            readable, _, _ = select([client_tls, origin_tls], [], [], 1.0)
            if not readable:
                idle_rounds += 1
                if idle_rounds > int(SOCKET_TIMEOUT * 3):
                    break
                continue
            idle_rounds = 0

            for current in readable:
                if current is client_tls:
                    data = client_tls.recv(BUFFER_SIZE)
                    if not data:
                        return
                    path, first_line = _extract_https_path_from_request(data)
                    log_message(f"HTTPS inspected request line: {first_line}")
                    full_url = f"https://{host}{path}"
                    allowed, reason = is_request_allowed(host, full_url)
                    if not allowed:
                        client_tls.sendall(create_error_response(403, "Forbidden"))
                        log_message(f"HTTPS request blocked: {reason} url={full_url}", "WARNING")
                        return
                    origin_tls.sendall(data)
                else:
                    data = origin_tls.recv(BUFFER_SIZE)
                    if not data:
                        return
                    client_tls.sendall(data)
    finally:
        try:
            if client_tls:
                client_tls.close()
        except Exception:
            pass
        try:
            if origin_tls:
                origin_tls.close()
        except Exception:
            pass
        try:
            if origin_tcp:
                origin_tcp.close()
        except Exception:
            pass


def handle_client(client_socket, client_address):
    """Handle one client request lifecycle safely."""
    client_ip = client_address[0]
    client_port = client_address[1]
    url_for_log = "-"
    status_for_log = "500"
    method_for_log = "-"
    protocol_for_log = "HTTP"
    target_host_for_log = "-"
    target_port_for_log = "-"
    request_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_for_log = "-"

    try:
        _increment_stat("total_requests")
        client_socket.settimeout(SOCKET_TIMEOUT)
        request_data = client_socket.recv(BUFFER_SIZE)
        if not request_data:
            status_for_log = "400"
            error_for_log = "empty_request"
            client_socket.sendall(create_error_response(400, "Bad Request"))
            return

        parsed = parse_http_request(request_data)
        if not parsed:
            status_for_log = "400"
            error_for_log = "malformed_request"
            client_socket.sendall(create_error_response(400, "Bad Request"))
            return

        method = parsed["method"]
        url = parsed["url"]
        host = parsed["host"]
        port = parsed["port"]
        method_for_log = method
        url_for_log = url
        target_host_for_log = host
        target_port_for_log = str(port)
        protocol_for_log = "HTTPS" if method == "CONNECT" or url.startswith("https://") else "HTTP"

        allowed, reason = is_request_allowed(host, url)
        if not allowed:
            _increment_stat("blocked_requests")
            status_for_log = "403"
            error_for_log = reason
            client_socket.sendall(create_error_response(403, "Forbidden"))
            return

        if method == "CONNECT":
            try:
                _mitm_https_tunnel(client_socket, host, port)
                status_for_log = "200"
                return
            except FileNotFoundError:
                _increment_stat("error_requests")
                status_for_log = "500"
                error_for_log = "missing_tls_certificate_or_key"
                client_socket.sendall(create_error_response(500, "TLS Certificate Missing"))
                return
            except ssl.SSLError:
                _increment_stat("error_requests")
                status_for_log = "502"
                error_for_log = "tls_handshake_failed"
                client_socket.sendall(create_error_response(502, "TLS Handshake Failed"))
                return
            except (socket.timeout, OSError, RuntimeError) as error:
                _increment_stat("error_requests")
                status_for_log = "502"
                error_for_log = str(error)
                client_socket.sendall(create_error_response(502, "HTTPS Tunnel Error"))
                return

        if CACHE_ENABLED and method == "GET":
            cached = shared_cache.get(url)
            if cached:
                _increment_stat("cache_hits")
                status_for_log = _extract_status_code(cached)
                client_socket.sendall(cached)
                log_message(f"Cache hit for URL: {url}")
                return

        try:
            response_data = _forward_request(host, port, request_data)
        except socket.timeout:
            _increment_stat("error_requests")
            status_for_log = "504"
            error_for_log = "origin_timeout"
            client_socket.sendall(create_error_response(504, "Gateway Timeout"))
            return
        except (socket.gaierror, ConnectionRefusedError, OSError):
            _increment_stat("error_requests")
            status_for_log = "502"
            error_for_log = "origin_connection_error"
            client_socket.sendall(create_error_response(502, "Bad Gateway"))
            return

        if not response_data:
            _increment_stat("error_requests")
            status_for_log = "502"
            error_for_log = "empty_origin_response"
            client_socket.sendall(create_error_response(502, "Bad Gateway"))
            return

        status_for_log = _extract_status_code(response_data)
        client_socket.sendall(response_data)

        if CACHE_ENABLED and method == "GET":
            shared_cache.put(url, response_data)
            log_message(f"Cached URL: {url}")

    except socket.timeout:
        _increment_stat("error_requests")
        status_for_log = "408"
        error_for_log = "client_timeout"
        try:
            client_socket.sendall(create_error_response(408, "Request Timeout"))
        except OSError:
            pass
    except Exception as error:
        _increment_stat("error_requests")
        error_for_log = str(error)
        log_message(f"Unhandled client error from {client_ip}: {error}", "ERROR")
        try:
            client_socket.sendall(create_error_response(500, "Internal Server Error"))
        except OSError:
            pass
    finally:
        response_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _record_request(
            {
                "client_ip": client_ip,
                "client_port": str(client_port),
                "target_host": target_host_for_log,
                "target_port": target_port_for_log,
                "method": method_for_log,
                "protocol": protocol_for_log,
                "url": url_for_log,
                "status": status_for_log,
                "request_time": request_timestamp,
                "response_time": response_timestamp,
                "error": error_for_log,
            }
        )
        log_request(client_ip, url_for_log, status_for_log)
        log_request_details(
            client_ip=client_ip,
            client_port=client_port,
            target_host=target_host_for_log,
            target_port=target_port_for_log,
            method=method_for_log,
            url=url_for_log,
            request_timestamp=request_timestamp,
            response_timestamp=response_timestamp,
            status=status_for_log,
            error_message=error_for_log,
        )
        try:
            client_socket.close()
        except OSError:
            pass
