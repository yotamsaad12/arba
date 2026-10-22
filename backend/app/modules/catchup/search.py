"""What to look for in a person's mailbox: mail about this project, and nothing else.

A mail is relevant when it names the project (permit or request number, block and parcel,
street address), or when it is from or to one of the area's approving bodies and is about
building (their other mail, such as property tax bills, stays out).
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import urlparse

from app.db.models import Project
from app.email.parsing import ParsedEmail
from app.modules.directory.schemas import AuthorityOut

# Building words, to tell an authority's permit mail from its other mail. Gmail matches whole
# words, so Hebrew forms with a prefix are listed too.
KEYWORDS = (
    "היתר",
    "ההיתר",
    "בנייה",
    "בניה",
    "טופס 4",
    "תעודת גמר",
    "אכלוס",
    "רישוי",
    "תיק מידע",
    "הנדסה",
    "פיקוח",
)
# Hosts in the directory that aren't the body's own mail domain.
_NOT_MAIL_DOMAINS = {"myvisit.com", "complot.co.il"}
# How far back to look when the permit date is unknown.
DEFAULT_LOOKBACK_YEARS = 6


@dataclass
class MailSearch:
    phrases: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    after: date | None = None

    def gmail_query(self) -> str:
        """Gmail search syntax: https://support.google.com/mail/answer/7190"""
        clauses = [_quote(p) for p in self.phrases]
        if self.domains:
            people = " OR ".join(f"from:{d} OR to:{d}" for d in self.domains)
            words = " OR ".join(_quote(k) for k in self.keywords)
            clauses.append(f"(({people}) ({words}))")
        query = "(" + " OR ".join(clauses) + ")" if clauses else ""
        if self.after:
            query += f" after:{self.after:%Y/%m/%d}"
        return query.strip()

    def matches(self, email: ParsedEmail) -> bool:
        """The same rule as `gmail_query`, for mailboxes searched here (the simulator)."""
        if self.after and email.sent_at.date() < self.after:
            return False
        text = _words(f"{email.subject}\n{email.text}")
        if any(_words(p) in text for p in self.phrases):
            return True
        addresses = [email.from_email, *email.to, *email.cc]
        from_body = any(_in_domain(a, d) for a in addresses for d in self.domains)
        return from_body and any(_words(k) in text for k in self.keywords)


def build_search(project: Project, authorities: list[AuthorityOut]) -> MailSearch:
    phrases = [project.permit_number, project.permit_request_number]
    if project.gush:
        phrases.append(f"גוש {project.gush}")
    street = _street(project.address)
    if street:
        phrases.append(street)

    domains: list[str] = []
    for a in authorities:
        hosts = [a.website, *(c.email for c in a.contacts), *(c.url for c in a.contacts)]
        for host in hosts:
            domain = _domain(host)
            if domain and domain not in domains:
                domains.append(domain)

    after = (
        project.permit_issue_date - timedelta(days=365 * 2)
        if project.permit_issue_date
        else date.today() - timedelta(days=365 * DEFAULT_LOOKBACK_YEARS)
    )
    return MailSearch(
        phrases=[p for p in dict.fromkeys(phrases) if p and len(p) >= 3],
        domains=domains,
        keywords=list(KEYWORDS),
        after=after,
    )


def _street(address: str | None) -> str | None:
    """'רחוב אחוזה 120, רעננה' -> 'אחוזה 120': specific enough to search for."""
    if not address:
        return None
    first = re.split(r"[,\n]", address)[0]
    first = re.sub(r"^\s*(רחוב|רח['׳]?|שדרות|שד['׳]?)\s+", "", first).strip()
    return first if re.search(r"\d", first) else None


def _domain(value: str | None) -> str | None:
    if not value:
        return None
    host = value.split("@", 1)[1] if "@" in value else urlparse(value).hostname or ""
    host = host.lower().removeprefix("www.")
    if not host or any(host == d or host.endswith("." + d) for d in _NOT_MAIL_DOMAINS):
        return None
    # The national gov.il umbrella is too broad; its units mail from their own subdomains.
    return None if host == "gov.il" else host


def _in_domain(address: str, domain: str) -> bool:
    host = address.rsplit("@", 1)[-1].lower()
    return host == domain or host.endswith("." + domain)


def _quote(text: str) -> str:
    return f'"{text}"' if " " in text else text


def _words(text: str) -> str:
    # Gmail matches phrases on words, ignoring punctuation; do the same.
    return " ".join(re.findall(r"\w+", text.lower()))
