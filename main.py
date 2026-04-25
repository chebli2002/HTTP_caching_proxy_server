"""
Program entry point for the modular HTTP proxy server.
Team attribution:
- Nabil: startup wiring and thread-driven server launch
- Chebli: runtime configuration usage
- John: startup logging context
"""

import os
import threading
import time

from config import BUFFER_SIZE, HOST, PORT, UI_HOST, UI_PORT
from logger import log_message
from server import HTTPProxyServer
from ui_server import start_ui_server


def main():
    """Create and run the proxy server."""
    os.makedirs(".", exist_ok=True)
    print("=" * 60)
    print("MODULAR HTTP PROXY SERVER")
    print("=" * 60)
    print(f"Host: {HOST}")
    print(f"Port: {PORT}")
    print(f"Buffer size: {BUFFER_SIZE}")
    print(f"Dashboard: http://{UI_HOST}:{UI_PORT}")
    print("Press Ctrl+C to stop")
    print("=" * 60)

    proxy_server = HTTPProxyServer(host=HOST, port=PORT, buffer_size=BUFFER_SIZE)
    try:
        proxy_thread = threading.Thread(target=proxy_server.start, daemon=True)
        proxy_thread.start()
        start_ui_server(host=UI_HOST, port=UI_PORT)
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
