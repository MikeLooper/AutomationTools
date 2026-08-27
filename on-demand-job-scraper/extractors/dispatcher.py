"""
extractors/dispatcher.py — Maps a URL's hostname to a predefined site module.

Unrecognized hostnames fall back to extractors.generic.
"""

from types import ModuleType
from urllib.parse import urlparse

from extractors import connectingcolorado, dice, generic, greenhouse, linkedin, remotive, topresume

_DOMAIN_MAP: dict[str, ModuleType] = {
    "jobs.connectingcolorado.gov": connectingcolorado,
    "connectingcolorado.gov": connectingcolorado,
    "dice.com": dice,
    "greenhouse.io": greenhouse,
    "linkedin.com": linkedin,
    "remotive.com": remotive,
    "careerio.topresume.com": topresume,
    "topresume.com": topresume,
}


def get_extractor(url: str) -> tuple[ModuleType, bool]:
    """Return (module, is_known_site) for the given URL."""
    hostname = urlparse(url).hostname or ""
    for suffix, module in _DOMAIN_MAP.items():
        if hostname == suffix or hostname.endswith("." + suffix):
            return module, True
    return generic, False
