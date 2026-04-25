"""
Filtering logic (blacklist/whitelist).
Team attribution:
- John: filtering implementation
- Chebli: parser integration inputs
- Nabil: server flow integration
"""

from config import BLACKLIST_DOMAINS, USE_WHITELIST, WHITELIST_DOMAINS


def is_domain_allowed(host):
    """Return True when request is allowed by filter rules."""
    if not host:
        return False

    normalized_host = host.lower()

    # If whitelist mode is on, host must appear in whitelist.
    if USE_WHITELIST:
        for allowed in WHITELIST_DOMAINS:
            if normalized_host == allowed or normalized_host.endswith("." + allowed):
                return True
        return False

    # Default mode: block hosts found in blacklist.
    for blocked in BLACKLIST_DOMAINS:
        if normalized_host == blocked or normalized_host.endswith("." + blocked):
            return False
    return True
