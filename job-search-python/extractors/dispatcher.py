"""
extractors/dispatcher.py — Maps a URL to the correct site extractor.
"""

from urllib.parse import urlparse

from extractors.base import BaseExtractor
from extractors.connectingcolorado import ConnectingColoradoExtractor
from extractors.dice import DiceExtractor
from extractors.glassdoor import GlassdoorExtractor
from extractors.greenhouse import GreenhouseExtractor
from extractors.linkedin import LinkedInExtractor
from extractors.remotive import RemotiveExtractor
from extractors.generic import GenericExtractor


_DOMAIN_MAP: dict[str, type[BaseExtractor]] = {
    "jobs.connectingcolorado.gov": ConnectingColoradoExtractor,
    "connectingcolorado.gov":      ConnectingColoradoExtractor,
    "dice.com":        DiceExtractor,
    "glassdoor.com":   GlassdoorExtractor,
    "greenhouse.io":   GreenhouseExtractor,
    "linkedin.com":    LinkedInExtractor,
    "remotive.com":    RemotiveExtractor,
}


def get_extractor(url: str) -> BaseExtractor:
    """Return the appropriate extractor for the given URL."""
    hostname = urlparse(url).hostname or ""
    # Strip leading 'www.' / 'my.' etc.
    for suffix, cls in _DOMAIN_MAP.items():
        if hostname.endswith(suffix):
            return cls()
    return GenericExtractor()
