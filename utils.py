"""
Utility helper functions.
Team attribution:
- Nabil: input validation helper reuse
- Chebli: HTTP helper reuse and adaptation
- John: shared formatting helpers for logs/errors
"""


def validate_port(port):
    """Validate port range and fallback to default lecture value."""
    try:
        parsed_port = int(port)
        if 1 <= parsed_port <= 65535:
            return parsed_port
    except ValueError:
        pass
    return 8888


def create_error_response(status_code, status_message):
    """Create a basic HTTP error response (lecture-style)."""
    body = (
        "<html>"
        f"<head><title>{status_code} {status_message}</title></head>"
        "<body>"
        f"<h1>{status_code} {status_message}</h1>"
        "<p>Proxy server could not fulfill the request.</p>"
        "<hr><p>Modular HTTP Proxy Server</p>"
        "</body></html>"
    )
    response = (
        f"HTTP/1.1 {status_code} {status_message}\r\n"
        "Content-Type: text/html\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
        f"{body}"
    )
    return response.encode()
