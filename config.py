"""
Configuration values for the modular HTTP proxy server.
Team attribution:
- Nabil: socket setup and multithreading defaults
- Chebli: parsing/proxy/cache configuration
- John: logging/filter configuration
"""

HOST = "127.0.0.1"
PORT = 8888
BUFFER_SIZE = 8192
BACKLOG = 5
SOCKET_TIMEOUT = 10.0

# Logging
LOG_FILE = "proxy.log"

# Cache settings (GET requests only)
CACHE_ENABLED = True
CACHE_TIMEOUT_SECONDS = 30

# Filtering settings
FILTER_ENABLED = True
USE_WHITELIST = False
WHITELIST_DOMAINS = [
    "example.com",
]
BLACKLIST_DOMAINS = [
    "blocked.com",
    "ads.badsite.com",
]

# Optional IP-based filtering (exact IPv4 string match).
WHITELIST_IPS = []
BLACKLIST_IPS = []

# Optional URL keyword filtering.
WHITELIST_URL_KEYWORDS = []
BLACKLIST_URL_KEYWORDS = []

# Web dashboard settings
UI_HOST = "127.0.0.1"
UI_PORT = 8080
