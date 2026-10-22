from typing import Any

from httpx import AsyncClient

from tests.conftest import auth, register

TEMPLATE_REQUIREMENTS = 45
PER_FLOOR_REQUIREMENTS = 5  # formwork, sleeves, rebar, photos, pour


async def create_project(client: AsyncClient, token: str, floors: int = 2) -> dict[str, Any]:
    templates = (await client.get("/api/v1/templates", headers=auth(token))).json()
    template = next(t for t in templates if t["key"] == "private_house")
    response = await client.post(
        "/api/v1/projects",
        headers=auth(token),
        json={
            "name": "הבית ברעננה",
            "template_id": template["id"],
            "municipality": "רעננה",
            "floors": floors,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def requirements(client: AsyncClient, token: str, project_id: str) -> list[dict[str, Any]]:
    response = await client.get(f"/api/v1/projects/{project_id}/requirements", headers=auth(token))
    return response.json()["requirements"]


def by_title(reqs: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    return next(r for r in reqs if r["title"].startswith(prefix))


async def set_status(
    client: AsyncClient, token: str, project_id: str, requirement_id: str, status: str
):
    return await client.patch(
        f"/api/v1/projects/{project_id}/requirements/{requirement_id}/status",
        headers=auth(token),
        json={"status": status},
    )


async def test_template_lists_with_counts(client: AsyncClient) -> None:
    token = await register(client)
    templates = (await client.get("/api/v1/templates", headers=auth(token))).json()
    assert [(t["key"], t["requirement_count"]) for t in templates] == [
        ("private_house", TEMPLATE_REQUIREMENTS)
    ]


async def test_project_gets_random_inbox_and_owner_role(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    assert project["role"] == "owner"
    assert project["inbox_address"].startswith("p-")
    assert project["inbox_address"].endswith("@in.arba.co.il")


async def test_skeleton_repeats_per_floor_and_chains_floors(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token, floors=2)
    reqs = await requirements(client, token, project["id"])
    assert len(reqs) == TEMPLATE_REQUIREMENTS + PER_FLOOR_REQUIREMENTS

    formwork_2 = next(r for r in reqs if r["title"].startswith("תבניות") and r["floor"] == 2)
    pour_1 = next(r for r in reqs if r["title"].startswith("יציקה ודגימות") and r["floor"] == 1)
    assert pour_1["id"] in formwork_2["depends_on"]


async def test_next_steps_on_a_new_project(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    steps = (
        await client.get(f"/api/v1/projects/{project['id']}/next-steps", headers=auth(token))
    ).json()

    ready = {r["title"] for r in steps["ready"]}
    assert "היתר בנייה בתוקף ורשימת התנאים שבו" in ready
    assert "חוזה עם הקבלן" in ready
    assert all(r["blocked_by"] for r in steps["blocked"])
    assert steps["progress"] == {"done": 0, "total": TEMPLATE_REQUIREMENTS + PER_FLOOR_REQUIREMENTS}

    reqs = {r["id"]: r for r in await requirements(client, token, project["id"])}
    path = steps["critical_path"]["requirement_ids"]
    assert reqs[path[-1]]["is_form4_gate"]
    assert steps["critical_path"]["remaining_days"] > 0


async def test_cannot_start_before_dependencies_are_done(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    reqs = await requirements(client, token, project["id"])
    permit, plans = by_title(reqs, "היתר בנייה"), by_title(reqs, "תיק תוכניות")
    assert plans["status"] == "blocked"

    response = await set_status(client, token, project["id"], plans["id"], "in_progress")
    assert response.status_code == 409
    assert response.json()["error"]["details"]["blocked_by"] == [permit["id"]]

    assert (await set_status(client, token, project["id"], permit["id"], "done")).status_code == 200
    plans = by_title(await requirements(client, token, project["id"]), "תיק תוכניות")
    assert plans["status"] == "ready"


async def test_reopening_a_dependency_flags_started_work(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    reqs = await requirements(client, token, project["id"])
    permit, plans = by_title(reqs, "היתר בנייה"), by_title(reqs, "תיק תוכניות")

    await set_status(client, token, project["id"], permit["id"], "done")
    await set_status(client, token, project["id"], plans["id"], "in_progress")
    await set_status(client, token, project["id"], permit["id"], "needs_fix")

    plans = by_title(await requirements(client, token, project["id"]), "תיק תוכניות")
    assert plans["status"] == "in_progress"
    assert plans["blocked_by"] == [permit["id"]]


async def test_only_optional_requirements_can_be_not_applicable(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    reqs = await requirements(client, token, project["id"])

    permit = by_title(reqs, "היתר בנייה")
    response = await set_status(client, token, project["id"], permit["id"], "not_applicable")
    assert response.status_code == 422

    fire = by_title(reqs, "אישור כבאות")
    response = await set_status(client, token, project["id"], fire["id"], "not_applicable")
    assert response.status_code == 200
    assert response.json()["status"] == "not_applicable"


async def test_automatic_statuses_cannot_be_set_by_hand(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    plans = by_title(await requirements(client, token, project["id"]), "תיק תוכניות")
    response = await set_status(client, token, project["id"], plans["id"], "ready")
    assert response.status_code == 422


async def test_projects_are_private_to_their_members(client: AsyncClient) -> None:
    owner = await register(client)
    project = await create_project(client, owner)
    stranger = await register(client, email="other@example.com")

    assert (await client.get("/api/v1/projects", headers=auth(stranger))).json() == []
    response = await client.get(f"/api/v1/projects/{project['id']}", headers=auth(stranger))
    assert response.status_code == 404


async def test_build_state_tracks_stages_floors_and_focus(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token, floors=2)
    build = project["build"]
    assert build["focus_stage"] == "pre"
    skeleton = sorted((s["floor"], s["total"]) for s in build["stages"] if s["stage"] == "skeleton")
    assert skeleton == [(1, PER_FLOOR_REQUIREMENTS), (2, PER_FLOOR_REQUIREMENTS)]

    fire = by_title(await requirements(client, token, project["id"]), "אישור כבאות")
    await set_status(client, token, project["id"], fire["id"], "not_applicable")
    detail = (await client.get(f"/api/v1/projects/{project['id']}", headers=auth(token))).json()
    form4 = next(s for s in detail["build"]["stages"] if s["stage"] == "form4")
    assert (form4["done"], form4["skipped"]) == (1, 1)
    assert detail["build"]["progress"]["done"] == 1
