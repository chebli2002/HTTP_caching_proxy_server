"""
Simple in-memory cache for GET responses.
Team attribution:
- Chebli: cache implementation and expiration logic
- Nabil: safe use in multithreaded server with lock
- John: cache logging integration
"""

import threading
import time

from config import CACHE_TIMEOUT_SECONDS


class SimpleCache:
    """Dictionary cache: key=url, value=(response_bytes, timestamp)."""

    def __init__(self, timeout_seconds=CACHE_TIMEOUT_SECONDS):
        self.cache = {}
        self.timeout_seconds = timeout_seconds
        self.lock = threading.Lock()

    def get(self, url):
        """Return cached response bytes or None if missing/expired."""
        with self.lock:
            entry = self.cache.get(url)
            if not entry:
                return None
            response_data, stored_at = entry
            if time.time() - stored_at > self.timeout_seconds:
                del self.cache[url]
                return None
            return response_data

    def put(self, url, response_data):
        """Store response bytes for a URL."""
        with self.lock:
            self.cache[url] = (response_data, time.time())
