"""
Socket server setup and client connection handling.
Team attribution:
- Nabil: socket setup + multithreading core
- Chebli: proxy handler integration
- John: server lifecycle logging integration
"""

import socket
import threading

from config import BACKLOG, BUFFER_SIZE, HOST, PORT
from logger import log_message
from proxy_handler import handle_client


class HTTPProxyServer:
    """Simple multithreaded HTTP proxy server."""

    def __init__(self, host=HOST, port=PORT, buffer_size=BUFFER_SIZE):
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.server_socket = None
        self.is_running = False

    def start(self):
        """Start listening and dispatch each client in a thread."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(BACKLOG)
        self.is_running = True

        log_message(f"Proxy server started on {self.host}:{self.port}")
        try:
            while self.is_running:
                client_socket, client_address = self.server_socket.accept()
                client_thread = threading.Thread(
                    target=handle_client,
                    args=(client_socket, client_address),
                    daemon=True,
                )
                client_thread.start()
        except KeyboardInterrupt:
            log_message("Keyboard interrupt received, shutting down.", "WARNING")
        except OSError as error:
            if self.is_running:
                log_message(f"Server socket error: {error}", "ERROR")
        finally:
            self.stop()

    def stop(self):
        """Stop server and close main socket."""
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
            self.server_socket = None
        log_message("Server stopped")
