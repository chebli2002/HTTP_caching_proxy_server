"""
Program entry point for the modular HTTP proxy server.
Team attribution:
- Nabil: startup wiring and thread-driven server launch
- Chebli: runtime configuration usage
- John: startup logging context
"""

import os
import time

from config import BUFFER_SIZE, HOST, PORT
from logger import log_message
from server import HTTPProxyServer


def main():
    """Create and run the proxy server."""
    os.makedirs(".", exist_ok=True)
    print("=" * 60)
    print("MODULAR HTTP PROXY SERVER")
    print("=" * 60)
    print(f"Host: {HOST}")
    print(f"Port: {PORT}")
    print(f"Buffer size: {BUFFER_SIZE}")
    print("Press Ctrl+C to stop")
    print("=" * 60)

    proxy_server = HTTPProxyServer(host=HOST, port=PORT, buffer_size=BUFFER_SIZE)
    try:
        proxy_server.start()
    except KeyboardInterrupt:
        log_message("Stopping server from main()", "WARNING")
        proxy_server.stop()
    except Exception as error:
        log_message(f"Fatal error in main: {error}", "ERROR")
        proxy_server.stop()
    finally:
        # Tiny sleep to allow background daemon threads to close sockets cleanly.
        time.sleep(0.1)


if __name__ == "__main__":
    main()
