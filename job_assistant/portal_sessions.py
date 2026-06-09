"""Portal detection and local session status helpers."""

from __future__ import annotations

from urllib.parse import urlparse


def detect_portal(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "linkedin" in host:
        return "LinkedIn"
    if "indeed" in host:
        return "Indeed"
    if "dice" in host:
        return "Dice"
    if "monster" in host:
        return "Monster"
    if "ziprecruiter" in host:
        return "ZipRecruiter"
    if "myworkdayjobs" in host or "workday" in host:
        return "Workday"
    if "greenhouse" in host:
        return "Greenhouse"
    if "lever.co" in host:
        return "Lever"
    if "icims" in host:
        return "iCIMS"
    if "taleo" in host:
        return "Taleo"
    if "successfactors" in host or "smartrecruiters" in host:
        return "SuccessFactors"
    if host:
        return "Company career sites"
    return "Unknown job sites"
