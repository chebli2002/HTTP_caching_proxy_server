"""
Proxy request/response handling module.
Team attribution:
- Chebli: proxy forwarding and cache flow
- Nabil: client socket lifecycle support
- John: logging + filtering integration
"""

import socket

from cache import SimpleCache
from config import BUFFER_SIZE, CACHE_ENABLED, SOCKET_TIMEOUT
from filter import is_domain_allowed
from logger import log_message, log_request
from parser import parse_http_request
from utils import create_error_response


shared_cache = SimpleCache()


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


def _forward_request(host, port, request_data):
    """Forward request to origin and return full response bytes."""
    origin_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    origin_socket.settimeout(SOCKET_TIMEOUT)
    try:
        origin_socket.connect((host, port))
        origin_socket.sendall(request_data)
        response_data = b""
        while True:
            chunk = origin_socket.recv(BUFFER_SIZE)
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
            status_for_log = "403"
            client_socket.sendall(create_error_response(403, "Forbidden"))
            return

        if CACHE_ENABLED and method == "GET":
            cached = shared_cache.get(url)
            if cached:
                status_for_log = _extract_status_code(cached)
                client_socket.sendall(cached)
                log_message(f"Cache hit for URL: {url}")
                return

        try:
            response_data = _forward_request(host, port, request_data)
        except socket.timeout:
            status_for_log = "504"
            client_socket.sendall(create_error_response(504, "Gateway Timeout"))
            return
        except (socket.gaierror, ConnectionRefusedError, OSError):
            status_for_log = "502"
            client_socket.sendall(create_error_response(502, "Bad Gateway"))
            return

        if not response_data:
            status_for_log = "502"
            client_socket.sendall(create_error_response(502, "Bad Gateway"))
            return

        status_for_log = _extract_status_code(response_data)
        client_socket.sendall(response_data)

        if CACHE_ENABLED and method == "GET":
            shared_cache.put(url, response_data)
            log_message(f"Cached URL: {url}")

    except socket.timeout:
        status_for_log = "408"
        try:
            client_socket.sendall(create_error_response(408, "Request Timeout"))
        except OSError:
            pass
    except Exception as error:
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
