#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HTTP Proxy Server
A simple multi-threaded HTTP proxy server for educational purposes.
Built from lecture materials on socket programming, HTTP, and networking.
"""

import socket
import threading
import datetime
import os
import sys

# ============================================================================
# BASIC SERVER SETUP
# ============================================================================

class HTTPProxyServer:
    """Simple HTTP proxy server that forwards requests to origin servers."""
    
    def __init__(self, host='127.0.0.1', port=8888, buffer_size=8192):
        """
        Initialize the proxy server.
        
        Args:
            host: Server bind address
            port: Server port number
            buffer_size: Socket receive buffer size
        """
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.server_socket = None
        self.is_running = False
        
    def start(self):
        """Start the proxy server and listen for incoming connections."""
        # Create TCP socket (AF_INET = IPv4, SOCK_STREAM = TCP)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # Allow reuse of address to avoid 'Address already in use' errors
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Bind socket to host and port
        self.server_socket.bind((self.host, self.port))
        
        # Listen for incoming connections (backlog of 5 pending connections)
        self.server_socket.listen(5)
        self.is_running = True
        
        self.log(f"Proxy server started on {self.host}:{self.port}")
        
        try:
            while self.is_running:
                # Accept client connection
                client_socket, client_address = self.server_socket.accept()
                self.log(f"New connection from {client_address}")
                
                # Create a new thread to handle this client
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address)
                )
                # Daemon thread exits when main thread exits
                client_thread.daemon = True
                client_thread.start()
                
        except KeyboardInterrupt:
            self.log("Shutting down server...")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the server and close the server socket."""
        self.is_running = False
        if self.server_socket:
            self.server_socket.close()
        self.log("Server stopped")

# ============================================================================
# CLIENT HANDLING
# ============================================================================

    def handle_client(self, client_socket, client_address):
        """
        Handle a single client connection.
        
        Args:
            client_socket: Socket connected to the client
            client_address: Address of the client
        """
        try:
            # Receive HTTP request from client
            request_data = client_socket.recv(self.buffer_size)
            
            if not request_data:
                self.log(f"Empty request from {client_address}", "WARNING")
                return
            
            # Parse the request to extract host and port
            request_text = request_data.decode('utf-8', errors='replace')
            self.log(f"Request from {client_address}:\n{request_text[:200]}...")
            
            # Extract host information from request
            host, port, request_line = self.parse_request(request_text)
            
            if not host:
                # Send error response if host cannot be determined
                error_response = self.create_error_response(400, "Bad Request")
                client_socket.send(error_response.encode())
                return
            
            # Forward the request to the origin server
            response_data = self.forward_request(host, port, request_data)
            
            # Send response back to client
            if response_data:
                client_socket.send(response_data)
                self.log(f"Sent response to {client_address} (size: {len(response_data)} bytes)")
            else:
                error_response = self.create_error_response(502, "Bad Gateway")
                client_socket.send(error_response.encode())
                
        except socket.timeout:
            self.log(f"Socket timeout from {client_address}", "ERROR")
        except ConnectionResetError:
            self.log(f"Connection reset by {client_address}", "ERROR")
        except Exception as e:
            self.log(f"Error handling client {client_address}: {e}", "ERROR")
        finally:
            client_socket.close()
            self.log(f"Closed connection from {client_address}")

# ============================================================================
# REQUEST PARSING
# ============================================================================

    def parse_request(self, request_text):
        """
        Parse HTTP request to extract host, port, and request line.
        
        Args:
            request_text: HTTP request as string
            
        Returns:
            tuple: (host, port, request_line)
        """
        lines = request_text.split('\r\n')
        if not lines:
            return None, None, None
        
        # Parse first line (request line)
        # Format: METHOD URL HTTP/VERSION
        request_line = lines[0]
        parts = request_line.split(' ')
        
        if len(parts) < 2:
            return None, None, None
        
        method = parts[0]
        url = parts[1]
        
        # Extract host and port from the request
        host = None
        port = 80  # Default HTTP port
        
        # Check for Host header (required in HTTP/1.1)
        for line in lines[1:]:
            if line.lower().startswith('host:'):
                host_header = line.split(':', 1)[1].strip()
                # Remove port if present in host header
                if ':' in host_header:
                    host, port_str = host_header.split(':', 1)
                    port = int(port_str)
                else:
                    host = host_header
                break
        
        # If no Host header, try to extract from URL
        if not host:
            if url.startswith('http://'):
                # URL format: http://hostname/path
                url_parts = url[7:].split('/', 1)
                host_part = url_parts[0]
                if ':' in host_part:
                    host, port_str = host_part.split(':', 1)
                    port = int(port_str)
                else:
                    host = host_part
        
        return host, port, request_line
    
    def forward_request(self, host, port, request_data):
        """
        Forward the HTTP request to the origin server.
        
        Args:
            host: Origin server hostname
            port: Origin server port
            request_data: Raw HTTP request bytes
            
        Returns:
            bytes: Response from origin server or None if error
        """
        try:
            # Create socket to connect to origin server
            origin_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            origin_socket.settimeout(10.0)  # 10 second timeout
            
            # Connect to origin server
            self.log(f"Connecting to {host}:{port}")
            origin_socket.connect((host, port))
            
            # Forward the request
            origin_socket.send(request_data)
            
            # Receive response
            response_data = b''
            while True:
                chunk = origin_socket.recv(self.buffer_size)
                if not chunk:
                    break
                response_data += chunk
            
            origin_socket.close()
            self.log(f"Received response from {host}:{port} (size: {len(response_data)} bytes)")
            
            return response_data
            
        except socket.timeout:
            self.log(f"Timeout connecting to {host}:{port}", "ERROR")
            return None
        except socket.gaierror:
            self.log(f"DNS resolution failed for {host}", "ERROR")
            return None
        except ConnectionRefusedError:
            self.log(f"Connection refused by {host}:{port}", "ERROR")
            return None
        except Exception as e:
            self.log(f"Error forwarding to {host}:{port}: {e}", "ERROR")
            return None
    
    def create_error_response(self, status_code, status_message):
        """
        Create an HTTP error response.
        
        Args:
            status_code: HTTP status code (e.g., 404)
            status_message: Human-readable status message
            
        Returns:
            str: HTTP error response
        """
        body = f"""
        <html>
        <head><title>{status_code} {status_message}</title></head>
        <body>
        <h1>{status_code} {status_message}</h1>
        <p>Proxy server could not fulfill the request.</p>
        <hr>
        <p>HTTP Proxy Server</p>
        </body>
        </html>
        """
        
        response = f"""HTTP/1.1 {status_code} {status_message}
Content-Type: text/html
Content-Length: {len(body)}
Connection: close

{body}"""
        return response

# ============================================================================
# LOGGING
# ============================================================================

    def log(self, message, level="INFO"):
        """
        Log a message with timestamp.
        
        Args:
            message: Log message
            level: Log level (INFO, WARNING, ERROR)
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
        
        # Optionally write to log file
        try:
            with open("proxy.log", "a") as log_file:
                log_file.write(f"[{timestamp}] [{level}] {message}\n")
        except IOError:
            pass  # Don't crash if logging fails

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def validate_port(port):
    """Validate that a port number is in the valid range."""
    try:
        port = int(port)
        if 1 <= port <= 65535:
            return port
        else:
            raise ValueError
    except ValueError:
        print(f"Invalid port number: {port}. Using default 8888.")
        return 8888

def main():
    """Main entry point for the proxy server."""
    # Default configuration
    HOST = '127.0.0.1'
    PORT = 8888
    BUFFER_SIZE = 8192
    
    # Override from command line if provided
    if len(sys.argv) > 1:
        PORT = validate_port(sys.argv[1])
    if len(sys.argv) > 2:
        BUFFER_SIZE = int(sys.argv[2])
    
    print("=" * 60)
    print("HTTP PROXY SERVER")
    print("=" * 60)
    print(f"Configuration:")
    print(f"  - Host: {HOST}")
    print(f"  - Port: {PORT}")
    print(f"  - Buffer size: {BUFFER_SIZE} bytes")
    print("\nTo use this proxy, configure your browser to use:")
    print(f"  HTTP Proxy: {HOST}  Port: {PORT}")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 60)
    
    # Create and start the proxy server
    proxy = HTTPProxyServer(host=HOST, port=PORT, buffer_size=BUFFER_SIZE)
    
    try:
        proxy.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        proxy.stop()
    except Exception as e:
        print(f"Fatal error: {e}")
        proxy.stop()
        sys.exit(1)

# ============================================================================
# SIMPLE CACHE IMPLEMENTATION (OPTIONAL EXTENSION)
# ============================================================================

class SimpleCache:
    """
    Simple in-memory cache for HTTP responses.
    Based on lecture discussion of Web caches (proxy servers).
    """
    
    def __init__(self, max_size_mb=100):
        """
        Initialize the cache.
        
        Args:
            max_size_mb: Maximum cache size in megabytes
        """
        self.cache = {}  # URL -> (response_data, timestamp, size)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.current_size_bytes = 0
    
    def get(self, url):
        """
        Retrieve a cached response if it exists.
        
        Args:
            url: Request URL
            
        Returns:
            bytes: Cached response or None if not cached
        """
        if url in self.cache:
            response_data, timestamp, _ = self.cache[url]
            # Could add TTL (Time To Live) checking here
            return response_data
        return None
    
    def put(self, url, response_data):
        """
        Store a response in the cache.
        
        Args:
            url: Request URL
            response_data: Response bytes to cache
        """
        data_size = len(response_data)
        
        # Simple size management - remove oldest if necessary
        while self.current_size_bytes + data_size > self.max_size_bytes:
            self.evict_oldest()
        
        self.cache[url] = (response_data, datetime.datetime.now(), data_size)
        self.current_size_bytes += data_size
    
    def evict_oldest(self):
        """Remove the oldest entry from the cache."""
        if not self.cache:
            return
        
        oldest_url = min(self.cache.keys(), 
                         key=lambda k: self.cache[k][1])
        _, _, size = self.cache.pop(oldest_url)
        self.current_size_bytes -= size
    
    def clear(self):
        """Clear all entries from the cache."""
        self.cache.clear()
        self.current_size_bytes = 0
    
    def get_size_mb(self):
        """Get current cache size in megabytes."""
        return self.current_size_bytes / (1024 * 1024)

# ============================================================================
# RUN THE SERVER
# ============================================================================

if __name__ == "__main__":
    main()