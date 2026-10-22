"""Loads the official reference snapshot (authorities, localities, planning committees) and the
curated contacts file into the database. Idempotent: safe to run on every deploy."""

import difflib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuthorityType, Channel, ContactSource
from app.db.models import (
    Authority,
    AuthorityArea,
    AuthorityContact,
    Locality,
    Municipality,
    PlanningCommittee,
)

DATA = Path(__file__).parent / "data"

_PREFIX = re.compile(
    r"^\s*(עיריית|עריית|עירית|מועצה אזורית|מועצה מקומית|מ\.?\s?א\.?|מ\.?\s?מ\.?\s?מ?\.?|מוא\"ז)\s+"
)
# Official names that changed or are spelled very differently between datasets.
_ALIASES = {"נצרתעילית": "נוףהגליל", "מראר": "מגאר", "רגר": "עגר", "גושחלב": "גש"}


def name_key(name: str) -> str:
    """Hebrew letters only, prefixes and doubled yod/vav removed: "עיריית קרית אתא" -> "קריתאתא"."""
    text = re.sub(r"\s*\(.*?\)?\s*$", "", name.strip())
    text = _PREFIX.sub("", text)
    text = re.sub(r"[^א-ת]", "", text)
    text = re.sub(r"יי+", "י", re.sub(r"וו+", "ו", text))
    return _ALIASES.get(text, text)


def same_name(a: str, b: str, cutoff: float = 0.8) -> bool:
    ka, kb = name_key(a), name_key(b)
    return bool(ka and kb) and (
        ka == kb or ka in kb or kb in ka or difflib.SequenceMatcher(None, ka, kb).ratio() >= cutoff
    )


class _Matcher:
    def __init__(self, municipalities: list[dict[str, Any]]):
        self.by_key: dict[str, dict[str, Any]] = {}
        for m in municipalities:
            for name in (m["name"], m["long_name"]):
                self.by_key.setdefault(name_key(name), m)

    def find(self, name: str) -> dict[str, Any] | None:
        key = name_key(name)
        if len(key) < 2:
            return None
        if key in self.by_key:
            return self.by_key[key]
        close = difflib.get_close_matches(key, self.by_key, n=1, cutoff=0.8)
        return self.by_key[close[0]] if close else None


def committee_title(name: str, kind: str) -> str:
    return f"הוועדה {'המרחבית' if kind == 'מרחבי' else 'המקומית'} לתכנון ובנייה {name}"


def reference_matcher() -> "_Matcher":
    """Name matching over the official authorities, for loading contacts on their own."""
    snapshot = json.loads((DATA / "reference.json").read_text(encoding="utf-8"))
    return _Matcher(snapshot["authorities"])


async def load_reference(db: AsyncSession) -> dict[str, int]:
    snapshot = json.loads((DATA / "reference.json").read_text(encoding="utf-8"))
    municipalities = snapshot["authorities"]
    matcher = _Matcher(municipalities)

    committees = {c["code"]: c for c in snapshot["committees"]}
    committee_of: dict[int, str] = {}
    for committee in snapshot["committees"]:
        for member in committee["members"]:
            m = matcher.find(member)
            if m:
                committee_of.setdefault(m["code"], committee["code"])

    # Authorities the planning map doesn't list (e.g. Judea and Samaria) act as their own
    # local committee. Marked "assumed" so the UI can say so.
    for m in municipalities:
        if m["code"] not in committee_of:
            code = f"M{m['code']}"
            committees[code] = {
                "code": code, "name": m["name"], "kind": "מקומי", "district": m["district"]
            }  # fmt: skip

    for c in committees.values():
        await db.execute(
            insert(PlanningCommittee)
            .values(code=c["code"], name=c["name"], kind=c["kind"], district=c["district"])
            .on_conflict_do_update(
                index_elements=["code"],
                set_={"name": c["name"], "kind": c["kind"], "district": c["district"]},
            )
        )

    for m in municipalities:
        official = committee_of.get(m["code"])
        assumed = f"M{m['code']}" if f"M{m['code']}" in committees else None
        values = {
            "name": m["name"],
            "long_name": m["long_name"],
            "kind": m["kind"],
            "district": m["district"],
            "committee_code": official or assumed,
            "committee_source": "planning_map" if official else "assumed" if assumed else None,
        }
        await db.execute(
            insert(Municipality)
            .values(code=m["code"], **values)
            .on_conflict_do_update(index_elements=["code"], set_=values)
        )

    codes = {m["code"] for m in municipalities}
    for loc in snapshot["localities"]:
        if loc["code"] in codes:
            owner: int | None = loc["code"]
        elif loc["regional_council"]:
            found = matcher.find(loc["regional_council"])
            owner = found["code"] if found else None
        else:
            owner = None
        values = {
            "name": loc["name"],
            "name_en": loc["name_en"] or None,
            "municipality_code": owner,
        }
        await db.execute(
            insert(Locality)
            .values(code=loc["code"], **values)
            .on_conflict_do_update(index_elements=["code"], set_=values)
        )

    # One Authority per committee, serving its member municipalities.
    members: dict[str, list[int]] = {}
    for m in municipalities:
        member_of: str | None = committee_of.get(m["code"]) or (
            f"M{m['code']}" if f"M{m['code']}" in committees else None
        )
        if member_of:
            members.setdefault(member_of, []).append(m["code"])
    for c in committees.values():
        authority = await _authority(
            db,
            AuthorityType.municipality,
            committee_title(c["name"], c["kind"]),
            committee=c["code"],
        )
        await db.execute(delete(AuthorityArea).where(AuthorityArea.authority_id == authority.id))
        db.add_all(
            AuthorityArea(authority_id=authority.id, municipality_code=code)
            for code in members.get(c["code"], [])
        )
    await db.flush()

    contacts = await load_contacts(db, matcher)
    await db.commit()
    return {
        "municipalities": len(municipalities),
        "localities": len(snapshot["localities"]),
        "committees": len(committees),
        "contacts": contacts,
    }


async def _authority(
    db: AsyncSession, type_: AuthorityType, name: str, *, committee: str | None = None
) -> Authority:
    authority = await db.scalar(
        select(Authority).where(Authority.type == type_, Authority.name == name)
    )
    if authority is None:
        authority = Authority(type=type_, name=name, committee_code=committee)
        db.add(authority)
        await db.flush()
    return authority


async def load_contacts(db: AsyncSession, matcher: _Matcher) -> int:
    """Applies contacts.yaml: official contacts are replaced from the file on every load;
    contacts people added or Arba learned are kept."""
    path = DATA / "contacts.yaml"
    if not path.exists():
        return 0
    entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    count = 0
    for entry in entries:
        if "committee" in entry:
            committee = await db.scalar(
                select(PlanningCommittee).where(PlanningCommittee.name == entry["committee"])
            )
            if committee is None:
                raise ValueError(f"contacts.yaml: unknown committee {entry['committee']}")
            authority = await _authority(
                db,
                AuthorityType.municipality,
                committee_title(committee.name, committee.kind),
                committee=committee.code,
            )
        else:
            authority = await _authority(db, AuthorityType(entry["type"]), entry["name"])
            authority.national = bool(entry.get("national"))
            await db.execute(
                delete(AuthorityArea).where(AuthorityArea.authority_id == authority.id)
            )
            for area in entry.get("areas") or []:
                m = matcher.find(area)
                if m is None:
                    raise ValueError(f"contacts.yaml: unknown municipality {area}")
                db.add(AuthorityArea(authority_id=authority.id, municipality_code=m["code"]))
        authority.website = entry.get("website") or authority.website
        authority.permit_search_url = entry.get("permit_search_url") or authority.permit_search_url
        authority.notes = entry.get("notes") or authority.notes

        await db.execute(
            delete(AuthorityContact).where(
                AuthorityContact.authority_id == authority.id,
                AuthorityContact.source == ContactSource.official_site,
            )
        )
        for c in entry.get("contacts") or []:
            db.add(
                AuthorityContact(
                    authority_id=authority.id,
                    purpose=c["purpose"],
                    channel=Channel(c.get("channel", "email")),
                    email=c.get("email"),
                    phone=c.get("phone"),
                    url=c.get("url"),
                    source=ContactSource.official_site,
                    source_url=c["source_url"],
                    verified_at=date.fromisoformat(str(c["verified_at"])),
                    notes=c.get("notes"),
                )
            )
            count += 1
    await db.flush()
    return count
