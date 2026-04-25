"""
Logging system for the proxy server.
Team attribution:
- John: main logging implementation
- Nabil/Chebli: integrated usage points across modules
"""

from datetime import datetime

from config import LOG_FILE


def log_message(message, level="INFO"):
    """General logger with timestamp and file append."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as log_file:
            log_file.write(line + "\n")
    except OSError:
        # Logging should never crash the server
        pass


def log_request(client_ip, url, status):
    """Specialized request log with required fields."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"client_ip={client_ip} url={url} status={status} timestamp={timestamp}"
    log_message(message, "INFO")


def log_request_details(
    client_ip,
    client_port,
    target_host,
    target_port,
    method,
    url,
    request_timestamp,
    response_timestamp,
    status,
    error_message="-",
):
    """Detailed request/response log line aligned with project requirements."""
    message = (
        f"client={client_ip}:{client_port} "
        f"target={target_host}:{target_port} "
        f"method={method} "
        f"url={url} "
        f"request_time={request_timestamp} "
        f"response_time={response_timestamp} "
        f"status={status} "
        f"error={error_message}"
    )
    log_message(message, "INFO")


def read_recent_logs(limit=50):
    """Return last log lines without crashing if file missing."""
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as log_file:
            lines = log_file.readlines()
            return lines[-limit:]
    except OSError:
        return []
