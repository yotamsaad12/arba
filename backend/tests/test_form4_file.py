"""The Form 4 file: by authority, shaped by the team, fed by the authorities' own lists."""

import io
from typing import Any

import openpyxl
from httpx import AsyncClient

from tests.conftest import auth, register
from tests.test_projects import by_title, create_project, requirements, set_status


async def building_project(client: AsyncClient, token: str, **fields: Any) -> dict[str, Any]:
    templates = (await client.get("/api/v1/templates", headers=auth(token))).json()
    template = next(t for t in templates if t["key"] == "residential_building")
    body = {
        "name": "פרויקט מגרש 149",
        "template_id": template["id"],
        "municipality": "באר שבע",
        "floors": 4,
        "plot_number": "149",
        **fields,
    }
    response = await client.post("/api/v1/projects", headers=auth(token), json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def form4(client: AsyncClient, token: str, project_id: str) -> dict[str, Any]:
    return (await client.get(f"/api/v1/projects/{project_id}/form4", headers=auth(token))).json()


async def test_a_developer_project_has_files_per_authority_and_building(
    client: AsyncClient,
) -> None:
    token = await register(client)
    project = await building_project(
        client, token, buildings=2, units=24, features=["elevator", "gas"]
    )
    assert (project["plot_number"], project["buildings"], project["units"]) == ("149", 2, 24)
    reqs = await requirements(client, token, project["id"])

    sealing = [r for r in reqs if r["title"].startswith("בדיקת אטימות מרחבים מוגנים")]
    assert sorted((r["building"], r["title"][-7:]) for r in sealing) == [
        (1, "בניין 1"),
        (2, "בניין 2"),
    ]
    assert by_title(reqs, "התאמת מעליות")["status"] != "not_applicable"
    assert by_title(reqs, "מערכת כיבוי אש אוטומטית")["status"] == "not_applicable"  # no sprinklers
    fire_doors = by_title(reqs, "התקנת דלתות אש")
    assert (fire_doors["track"], fire_doors["standard"]) == ("fire", 'ת"י 1212 חלק 4.4')

    tracks = {t["track"]: t for t in (await form4(client, token, project["id"]))["tracks"]}
    assert set(tracks) >= {"municipality", "fire", "home_front", "telecom", "water", "gas"}
    assert tracks["fire"]["total"] == 17


async def test_the_team_shapes_the_list(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    pid = project["id"]
    added = await client.post(
        f"/api/v1/projects/{pid}/requirements",
        headers=auth(token),
        json={
            "title": "אישור מחלקת גנים ונוף",
            "track": "municipality",
            "appendix": "נספח 27",
            "notes": "נשלח למורין",
        },
    )
    assert added.status_code == 201, added.text
    item = added.json()
    assert (item["origin"], item["appendix"], item["stage"]) == ("user", "נספח 27", "form4")
    gate = next(r for r in await requirements(client, token, pid) if r["is_form4_gate"])
    assert item["id"] in gate["depends_on"]

    edited = await client.patch(
        f"/api/v1/projects/{pid}/requirements/{item['id']}",
        headers=auth(token),
        json={"notes": "התקבל", "due_date": "2026-12-01"},
    )
    assert (edited.json()["notes"], edited.json()["due_date"]) == ("התקבל", "2026-12-01")

    standard = by_title(await requirements(client, token, pid), "תמונות חזיתות")
    refused = await client.delete(
        f"/api/v1/projects/{pid}/requirements/{standard['id']}", headers=auth(token)
    )
    assert refused.json()["error"]["code"] == "template_item"
    removed = await client.delete(
        f"/api/v1/projects/{pid}/requirements/{item['id']}", headers=auth(token)
    )
    assert removed.status_code == 204


async def test_features_switch_items_on_and_off(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    pool = by_title(await requirements(client, token, project["id"]), "אישור יועץ בטיחות לבריכה")
    assert pool["status"] == "not_applicable"

    await client.patch(
        f"/api/v1/projects/{project['id']}", headers=auth(token), json={"features": ["pool"]}
    )
    pool = by_title(await requirements(client, token, project["id"]), "אישור יועץ בטיחות לבריכה")
    assert pool["status"] in ("blocked", "ready", "not_started")

    await client.patch(
        f"/api/v1/projects/{project['id']}", headers=auth(token), json={"features": []}
    )
    pool = by_title(await requirements(client, token, project["id"]), "אישור יועץ בטיחות לבריכה")
    assert pool["status"] == "not_applicable"


async def test_an_authoritys_whole_file_completes_its_approval(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    reqs = await requirements(client, token, project["id"])
    home_front = [r for r in reqs if r["track"] == "home_front"]
    approval = by_title(reqs, 'אישור פיקוד העורף לממ"ד')
    assert approval["fulfilled_by_track"] == "home_front"

    for item in home_front:
        await set_status(client, token, project["id"], item["id"], "not_applicable")
    approval = by_title(await requirements(client, token, project["id"]), 'אישור פיקוד העורף לממ"ד')
    assert approval["status"] == "done"
    tracks = {t["track"]: t for t in (await form4(client, token, project["id"]))["tracks"]}
    assert tracks["home_front"]["complete"] and approval["id"] in tracks["home_front"]["fulfils"]


def _workbook() -> bytes:
    """An authority list in the shape teams keep them: a sheet per authority."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "עירייה"
    sheet.append(["בדיקות עירייה"])
    sheet.append(["מס'", "הבדיקה", "סטטוס"])
    sheet.append([1, "תכנית עדות - מודד", "נספח 20"])
    sheet.append([2, "אישור חשמלאי מוסמך", "נספח 33"])
    sheet.append([3, "אישור מחלקת גנים ונוף", "נשלח לרונית"])
    sheet.append([4, "אישור הוט", "אין צורך"])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


async def test_an_authority_list_is_imported_with_approval(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    pid = project["id"]
    response = await client.post(
        f"/api/v1/projects/{pid}/checklist/imports",
        headers=auth(token),
        files={
            "file": (
                "דרישות עירייה.xlsx",
                _workbook(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 201, response.text
    imported = response.json()
    proposals = {i["title"]: i for i in imported["items"]}
    assert proposals["תכנית עדות - מודד"]["match_title"].startswith("תוכנית עדות (AS MADE)")
    assert proposals["אישור מחלקת גנים ונוף"]["match_requirement_id"] is None
    assert proposals["אישור הוט"]["not_needed"] is True

    applied = await client.post(
        f"/api/v1/projects/{pid}/checklist/imports/{imported['id']}/apply",
        headers=auth(token),
        json={},
    )
    assert {i["status"] for i in applied.json()["items"]} == {"merged", "added"}
    reqs = await requirements(client, token, pid)
    assert by_title(reqs, "תוכנית עדות (AS MADE)")["appendix"] == "20"
    gardens = by_title(reqs, "אישור מחלקת גנים ונוף")
    assert (gardens["origin"], gardens["notes"]) == ("authority_list", "נשלח לרונית")
    assert by_title(reqs, "אישור הוט")["status"] == "not_applicable"

    # The list itself is kept in the file, under the step for the authority's list.
    docs = (await client.get(f"/api/v1/projects/{pid}/documents", headers=auth(token))).json()
    form4_list = by_title(reqs, "קבלת רשימת האישורים לטופס 4")
    assert [d["requirement_id"] for d in docs] == [form4_list["id"]]
