"""Job URL extraction with safe fallback behavior."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from html import unescape
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import re


FALLBACK_MESSAGE = (
    "Unable to extract full job details from URL. Please paste the job description manually."
)


@dataclass
class ExtractedJobDetails:
    job_title: str = ""
    company_name: str = ""
    job_url: str = ""
    source: str = ""
    location: str = ""
    work_mode: str = ""
    employment_type: str = ""
    salary_range: str = ""
    full_job_description: str = ""
    responsibilities: list[str] | None = None
    required_qualifications: list[str] | None = None
    preferred_qualifications: list[str] | None = None
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    benefits: list[str] | None = None
    visible_application_questions: list[dict[str, object]] | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        for key in (
            "responsibilities",
            "required_qualifications",
            "preferred_qualifications",
            "required_skills",
            "preferred_skills",
            "benefits",
            "visible_application_questions",
        ):
            if payload[key] is None:
                payload[key] = []
        return payload


class _ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        if tag in {"p", "br", "li", "div", "section", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        if tag in {"p", "li", "div", "section", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        text = unescape(" ".join(self.parts))
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)


def _fetch_url(url: str, timeout: int = 10) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "JobApplicationAssistant/1.0 (+manual user review)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            raise ValueError("URL did not return an HTML page")
        return response.read(1_500_000).decode("utf-8", errors="replace")


def _source(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if "linkedin" in host:
        return "linkedin"
    if "indeed" in host:
        return "indeed"
    if "glassdoor" in host:
        return "glassdoor"
    if "dice" in host:
        return "dice"
    if "monster" in host:
        return "monster"
    if "careerbuilder" in host:
        return "careerbuilder"
    if "ziprecruiter" in host:
        return "ziprecruiter"
    return host or "company_career_portal"


def _meta(html: str, *names: str) -> str:
    for name in names:
        patterns = [
            rf'<meta[^>]+(?:name|property)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']{re.escape(name)}["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, flags=re.IGNORECASE)
            if match:
                return unescape(match.group(1)).strip()
    return ""


def _title_from_html(html: str) -> str:
    title = _meta(html, "og:title", "twitter:title")
    if title:
        return title
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    return unescape(re.sub(r"\s+", " ", match.group(1)).strip()) if match else ""


def _split_lines(text: str) -> list[str]:
    candidates = re.split(r"\n| • | \u2022 | - ", text)
    return [item.strip(" :-\t") for item in candidates if len(item.strip()) > 3]


def _section(text: str, headings: list[str], stop_headings: list[str]) -> list[str]:
    heading_pattern = "|".join(re.escape(item) for item in headings)
    stop_pattern = "|".join(re.escape(item) for item in stop_headings)
    match = re.search(
        rf"({heading_pattern})[:\s]*(.*?)(?=\n(?:{stop_pattern})[:\s]|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    return _split_lines(match.group(2))[:12]


def _salary(text: str) -> str:
    patterns = [
        r"\$[0-9][0-9,]*(?:\s*-\s*\$?[0-9][0-9,]*)?(?:\s*(?:per year|annually|/year|/yr|hourly|/hour|/hr))?",
        r"[0-9]{2,3}k\s*-\s*[0-9]{2,3}k",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return ""


def _work_mode(text: str) -> str:
    lowered = text.lower()
    if "remote" in lowered:
        return "Remote"
    if "hybrid" in lowered:
        return "Hybrid"
    if "on-site" in lowered or "onsite" in lowered:
        return "On-site"
    return ""


def _employment_type(text: str) -> str:
    for value in ["Full-time", "Part-time", "Contract", "Temporary", "Internship"]:
        if value.lower() in text.lower():
            return value
    return ""


def _questions(text: str) -> list[dict[str, object]]:
    questions = []
    for match in re.finditer(r"([^.\n?!]{10,160}\?)", text):
        question = re.sub(r"\s+", " ", match.group(1)).strip()
        if question.lower() not in {item["question"].lower() for item in questions}:
            questions.append({"question": question, "options": []})
        if len(questions) >= 20:
            break
    return questions


def _blocked(html: str, text: str) -> bool:
    lowered = f"{html[:2000]} {text[:2000]}".lower()
    indicators = [
        "captcha",
        "verify you are human",
        "enable javascript",
        "sign in to view",
        "login to continue",
        "access denied",
        "unusual traffic",
    ]
    return any(indicator in lowered for indicator in indicators)


def extract_job_from_url(
    url: str,
    fetcher: Callable[[str], str] | None = None,
) -> dict[str, object]:
    """Fetch a user-provided job URL and extract visible job details.

    This performs a simple, non-stealth HTML fetch. It does not render JavaScript,
    bypass login, solve CAPTCHA, or evade protections.
    """

    fetch = fetcher or _fetch_url
    try:
        html = fetch(url)
        parser = _ReadableHTMLParser()
        parser.feed(html)
        text = parser.text()
        if len(text) < 150 or _blocked(html, text):
            raise ValueError("Page requires login, CAPTCHA, JavaScript, or blocks extraction")
    except Exception:
        return {
            "success": False,
            "message": FALLBACK_MESSAGE,
            "job_url": url,
            "source": _source(url),
        }

    title = _title_from_html(html)
    title_parts = re.split(r"\s+[-|]\s+", title)
    job_title = title_parts[0].strip() if title_parts else ""
    company_name = title_parts[1].strip() if len(title_parts) > 1 else _meta(html, "og:site_name")
    stop_headings = [
        "Responsibilities",
        "Requirements",
        "Required Qualifications",
        "Preferred Qualifications",
        "Qualifications",
        "Skills",
        "Benefits",
        "About",
        "Apply",
    ]
    responsibilities = _section(text, ["Responsibilities", "What you will do", "Duties"], stop_headings)
    required = _section(text, ["Required Qualifications", "Requirements", "Minimum Qualifications"], stop_headings)
    preferred = _section(text, ["Preferred Qualifications", "Preferred"], stop_headings)
    benefits = _section(text, ["Benefits", "Perks"], stop_headings)
    skills_text = "\n".join(required + preferred + responsibilities + [text])
    from .keywords import extract_known_skills

    all_skills = extract_known_skills(skills_text)
    required_skills = extract_known_skills("\n".join(required)) or all_skills[:10]
    preferred_skills = [skill for skill in extract_known_skills("\n".join(preferred)) if skill not in required_skills]

    return {
        "success": True,
        "message": "",
        **ExtractedJobDetails(
            job_title=job_title,
            company_name=company_name,
            job_url=url,
            source=_source(url),
            location=_meta(html, "jobLocation", "og:locality"),
            work_mode=_work_mode(text),
            employment_type=_employment_type(text),
            salary_range=_salary(text),
            full_job_description=text,
            responsibilities=responsibilities,
            required_qualifications=required,
            preferred_qualifications=preferred,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            benefits=benefits,
            visible_application_questions=_questions(text),
        ).to_dict(),
    }
