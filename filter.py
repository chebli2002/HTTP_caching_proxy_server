"""
Filtering logic (blacklist/whitelist).
Team attribution:
- John: filtering implementation
- Chebli: parser integration inputs
- Nabil: server flow integration
"""

import socket

from config import (
    BLACKLIST_DOMAINS,
    BLACKLIST_IPS,
    BLACKLIST_URL_KEYWORDS,
    FILTER_ENABLED,
    USE_WHITELIST,
    WHITELIST_DOMAINS,
    WHITELIST_IPS,
    WHITELIST_URL_KEYWORDS,
)


def _match_domain(host, domains):
    for domain in domains:
        normalized_domain = domain.lower()
        if host == normalized_domain or host.endswith("." + normalized_domain):
            return True
    return False


def _resolve_host_ip(host):
    try:
        return socket.gethostbyname(host)
    except OSError:
        return None


def _match_url(url, keywords):
    lowered_url = url.lower()
    for keyword in keywords:
        if keyword.lower() in lowered_url:
            return True
    return False


def is_request_allowed(host, url):
    """
    Return (is_allowed, reason).
    Supports domain, IP, and URL keyword filtering.
    """
    if not FILTER_ENABLED:
        return True, "filter_disabled"

    if not host:
        return False, "missing_host"

    normalized_host = host.lower()
    resolved_ip = _resolve_host_ip(normalized_host)

    # If whitelist mode is on, host must appear in whitelist.
    if USE_WHITELIST:
        domain_ok = _match_domain(normalized_host, WHITELIST_DOMAINS)
        ip_ok = resolved_ip in WHITELIST_IPS if resolved_ip else False
        url_ok = _match_url(url, WHITELIST_URL_KEYWORDS) if WHITELIST_URL_KEYWORDS else False
        if domain_ok or ip_ok or url_ok:
            return True, "whitelist_match"
        return False, "not_in_whitelist"

    # Default mode: block hosts found in blacklist.
    if _match_domain(normalized_host, BLACKLIST_DOMAINS):
        return False, "blacklisted_domain"
    if resolved_ip and resolved_ip in BLACKLIST_IPS:
        return False, "blacklisted_ip"
    if _match_url(url, BLACKLIST_URL_KEYWORDS):
        return False, "blacklisted_url"
    return True, "allowed"
