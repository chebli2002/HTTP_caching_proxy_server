"""
Proxy request/response handling module.
Team attribution:
- Chebli: proxy forwarding and cache flow
- Nabil: client socket lifecycle support
- John: logging + filtering integration
"""

import socket
import threading

from cache import SimpleCache
from config import BUFFER_SIZE, CACHE_ENABLED, SOCKET_TIMEOUT
from filter import is_domain_allowed
from logger import log_message, log_request
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


def handle_client(client_socket, client_address):
    """Handle one client request lifecycle safely."""
    client_ip = client_address[0]
    url_for_log = "-"
    status_for_log = "500"

    try:
        _increment_stat("total_requests")
        client_socket.settimeout(SOCKET_TIMEOUT)
        request_data = client_socket.recv(BUFFER_SIZE)
        if not request_data:
            status_for_log = "400"
            client_socket.sendall(create_error_response(400, "Bad Request"))
            return

        parsed = parse_http_request(request_data)
        if not parsed:
            status_for_log = "400"
            client_socket.sendall(create_error_response(400, "Bad Request"))
            return

        method = parsed["method"]
        url = parsed["url"]
        host = parsed["host"]
        port = parsed["port"]
        url_for_log = url

        if not is_domain_allowed(host):
            _increment_stat("blocked_requests")
            status_for_log = "403"
            client_socket.sendall(create_error_response(403, "Forbidden"))
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
            client_socket.sendall(create_error_response(504, "Gateway Timeout"))
            return
        except (socket.gaierror, ConnectionRefusedError, OSError):
            _increment_stat("error_requests")
            status_for_log = "502"
            client_socket.sendall(create_error_response(502, "Bad Gateway"))
            return

        if not response_data:
            _increment_stat("error_requests")
            status_for_log = "502"
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
        try:
            client_socket.sendall(create_error_response(408, "Request Timeout"))
        except OSError:
            pass
    except Exception as error:
        _increment_stat("error_requests")
        log_message(f"Unhandled client error from {client_ip}: {error}", "ERROR")
        try:
            client_socket.sendall(create_error_response(500, "Internal Server Error"))
        except OSError:
            pass
    finally:
        log_request(client_ip, url_for_log, status_for_log)
        try:
            client_socket.close()
        except OSError:
            pass
