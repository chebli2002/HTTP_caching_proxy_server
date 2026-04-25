"""
HTTP request parsing module.
Team attribution:
- Chebli: parsing implementation
- Nabil: thread-safe usage context
- John: logging-related parsed output fields
"""


def parse_http_request(request_data):
    """
    Parse raw HTTP request bytes into method, URL, host, port and request line.
    Returns None on malformed requests.
    """
    if not request_data:
        return None

    try:
        request_text = request_data.decode("utf-8", errors="replace")
    except Exception:
        return None

    lines = request_text.split("\r\n")
    if not lines or not lines[0]:
        return None

    request_line = lines[0]
    parts = request_line.split(" ")
    if len(parts) < 3:
        return None

    method = parts[0].strip().upper()
    url = parts[1].strip()
    version = parts[2].strip()

    host = None
    port = 80

    for line in lines[1:]:
        if line.lower().startswith("host:"):
            host_header = line.split(":", 1)[1].strip()
            if ":" in host_header:
                host_part, port_part = host_header.rsplit(":", 1)
                host = host_part.strip()
                try:
                    port = int(port_part)
                except ValueError:
                    return None
            else:
                host = host_header
            break

    if not host and url.startswith("http://"):
        host_path = url[7:]
        host_part = host_path.split("/", 1)[0]
        if ":" in host_part:
            host_name, port_text = host_part.rsplit(":", 1)
            host = host_name
            try:
                port = int(port_text)
            except ValueError:
                return None
        else:
            host = host_part

    if not host:
        return None

    return {
        "method": method,
        "url": url,
        "version": version,
        "host": host,
        "port": port,
        "request_line": request_line,
    }
