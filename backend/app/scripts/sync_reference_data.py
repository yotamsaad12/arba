"""Refreshes the official reference data snapshot that the directory is built on.

    python -m app.scripts.sync_reference_data

Sources (all official and public):
- data.gov.il, local authorities (Digital Israel): code, name, type, district.
- data.gov.il, localities (Population Authority): locality code, name, regional council.
- Planning Administration map service, planning areas: which local/regional committee covers
  which authorities.

The snapshot is committed to the repo (app/modules/directory/data/reference.json): servers don't
need to reach these sites (data.gov.il blocks some regions), and tests stay offline.
"""

import json
import ssl
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import certifi
import httpx

OUT = Path(__file__).resolve().parents[1] / "modules" / "directory" / "data" / "reference.json"
CKAN = "https://data.gov.il/api/3/action"
PLANNING_AREAS = "https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/gvulot_retzef/MapServer/3/query"


def _resource_id(client: httpx.Client, package: str) -> str:
    """Resource ids change when a dataset is republished; look up the current CSV."""
    data = client.get(f"{CKAN}/package_show", params={"id": package}).json()["result"]
    return next(r["id"] for r in data["resources"] if r.get("format", "").upper() == "CSV")


def _records(client: httpx.Client, resource_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while True:
        page = client.get(
            f"{CKAN}/datastore_search",
            params={"resource_id": resource_id, "limit": 1000, "offset": len(out)},
        ).json()["result"]
        out += page["records"]
        if len(out) >= page["total"] or not page["records"]:
            return out


def _clean(value: Any) -> str:
    return str(value or "").strip()


def main() -> None:
    with httpx.Client(timeout=60, headers={"User-Agent": "Arba reference sync"}) as client:
        authorities = [
            {
                "code": int(r["LocalAuthorityCode"]),
                "name": _clean(r["LocalAuthorityName"]),
                "long_name": _clean(r["LocalAuthorityLongName"]),
                "kind": _clean(r["LocalAuthorityType"]),
                "district": _clean(r["LocalAuthorityDistrict"]),
            }
            for r in _records(client, _resource_id(client, "municipal-authorities"))
        ]
        localities = [
            {
                "code": int(r["סמל_ישוב"]),
                "name": _clean(r["שם_ישוב"]),
                "name_en": _clean(r["שם_ישוב_לועזי"]).title(),
                "regional_council_code": int(r["סמל_מועצה_איזורית"] or 0) or None,
                "regional_council": _clean(r["שם_מועצה"]) or None,
            }
            for r in _records(client, _resource_id(client, "citiesandsettelments"))
            if _clean(r["שם_ישוב"])
        ]
    # The Planning Administration's server only negotiates older ciphers; certificates are still
    # fully verified.
    planning_tls = ssl.create_default_context(cafile=certifi.where())
    planning_tls.set_ciphers("DEFAULT@SECLEVEL=1")
    with httpx.Client(timeout=60, verify=planning_tls) as client:
        areas = client.get(
            PLANNING_AREAS,
            params={
                "where": "1=1",
                "outFields": "MT_Heb,Sug_MT,Machoz,CodeMT,Muni_In_MT",
                "returnGeometry": "false",
                "f": "json",
            },
        ).json()["features"]

    committees: dict[str, dict[str, Any]] = {}
    for feature in areas:
        a = feature["attributes"]
        code = _clean(a["CodeMT"])
        if not code:
            continue
        committee = committees.setdefault(
            code,
            {
                "code": code,
                "name": _clean(a["MT_Heb"]),
                "kind": _clean(a["Sug_MT"]),
                "district": _clean(a["Machoz"]),
                "members": [],
            },
        )
        for member in _clean(a["Muni_In_MT"]).split(","):
            if member.strip() and member.strip() not in committee["members"]:
                committee["members"].append(member.strip())

    snapshot = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sources": {
            "authorities": "https://data.gov.il/dataset/municipal-authorities",
            "localities": "https://data.gov.il/dataset/citiesandsettelments",
            "planning_areas": PLANNING_AREAS.removesuffix("/query"),
        },
        "authorities": sorted(authorities, key=lambda a: str(a["code"]).zfill(8)),
        "localities": sorted(localities, key=lambda loc: str(loc["code"]).zfill(8)),
        "committees": sorted(committees.values(), key=lambda c: str(c["code"]).zfill(8)),
    }
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(
        f"wrote {OUT.name}: {len(authorities)} authorities, {len(localities)} localities, "
        f"{len(committees)} committees"
    )


if __name__ == "__main__":
    main()
