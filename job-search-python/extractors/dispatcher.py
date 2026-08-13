"""
extractors/dispatcher.py — Maps a URL to the correct site extractor.
"""

from urllib.parse import urlparse
from typing import Optional

from extractors.base import BaseExtractor
from extractors.connectingcolorado import ConnectingColoradoExtractor
from extractors.dice import DiceExtractor
from extractors.glassdoor import GlassdoorExtractor
from extractors.greenhouse import GreenhouseExtractor
from extractors.linkedin import LinkedInExtractor
from extractors.remotive import RemotiveExtractor
from extractors.topresume import TopResumeExtractor


_DOMAIN_MAP: dict[str, type[BaseExtractor]] = {
    "jobs.connectingcolorado.gov": ConnectingColoradoExtractor,
    "connectingcolorado.gov":      ConnectingColoradoExtractor,
    "dice.com":        DiceExtractor,
    "glassdoor.com":   GlassdoorExtractor,
    "greenhouse.io":   GreenhouseExtractor,
    "linkedin.com":    LinkedInExtractor,
    "remotive.com":    RemotiveExtractor,
    "careerio.topresume.com": TopResumeExtractor,
    "topresume.com": TopResumeExtractor,
}


def get_extractor(url: str) -> Optional[BaseExtractor]:
    """Return a site extractor for known domains, else None."""
    hostname = urlparse(url).hostname or ""
    # Strip leading 'www.' / 'my.' etc.
    for suffix, cls in _DOMAIN_MAP.items():
        if hostname.endswith(suffix):
            return cls()
    return None
