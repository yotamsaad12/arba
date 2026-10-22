"""The checklist is complete: permit conditions, the authority's own list, and what authorities
ask for along the way."""

from typing import Any

import pytest
from httpx import AsyncClient

from app.core.enums import AuthorityType, ConditionTiming
from app.modules.permits import conditions
from app.modules.permits.conditions import FoundCondition, conditions_from_text
from tests.conftest import auth, register
from tests.test_inbox import deliver, email
from tests.test_permits_directory import RAANANA, new_project, upload_permit
from tests.test_projects import by_title, requirements
from tests.test_suggestions import pending

YEROHAM = 831

FOUND = [
    FoundCondition(
        number="7",
        text="שמירה על עץ הזית הקיים בחזית המגרש לפי הנחיות פקיד היערות.",
        title="שמירה על עץ הזית בחזית",
        timing=ConditionTiming.before_form4,
        stage="form4",
        authority_type=AuthorityType.municipality,
        documents=["אישור פקיד היערות"],
        matches=None,
    ),
    FoundCondition(
        number="9",
        text="לפני תעודת גמר יש להציג אישור תאגיד המים על חיבור לביוב.",
        title="אישור תאגיד המים",
        timing=ConditionTiming.before_form4,
        stage="form4",
        authority_type=AuthorityType.water_corporation,
        documents=["אישור חיבור לביוב"],
        matches=None,
    ),
]


async def conditions_of(client: AsyncClient, token: str, project_id: str) -> dict[str, Any]:
    response = await client.get(
        f"/api/v1/projects/{project_id}/permit/conditions", headers=auth(token)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_permit_conditions_become_steps_after_approval(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_read(*_: Any) -> tuple[list[FoundCondition], str]:
        return [c.model_copy() for c in FOUND], "claude"

    monkeypatch.setattr(conditions, "read", fake_read)
    token = await register(client)
    project = await new_project(client, token, locality_code=RAANANA)
    assert (await conditions_of(client, token, project["id"]))["status"] is None

    # Uploading the permit and checking it starts reading the conditions.
    await upload_permit(client, token, project["id"])
    await client.post(f"/api/v1/projects/{project['id']}/permit/check", headers=auth(token))
    found = await conditions_of(client, token, project["id"])
    assert found["status"] == "ready"
    tree, water = found["conditions"]
    assert tree["match_requirement_id"] is None
    # The water condition belongs to the existing water corporation step.
    assert water["requirement_title"] == "אישור חיבור למים וביוב מתאגיד המים"

    response = await client.post(
        f"/api/v1/projects/{project['id']}/permit/conditions/accept-all", headers=auth(token)
    )
    assert {c["status"] for c in response.json()["conditions"]} == {"accepted"}

    reqs = await requirements(client, token, project["id"])
    new = by_title(reqs, "שמירה על עץ הזית בחזית")
    assert new["stage"] == "form4" and new["required_documents"] == ["אישור פקיד היערות"]
    gate = next(r for r in reqs if r["is_form4_gate"])
    assert new["id"] in gate["depends_on"]
    water_step = by_title(reqs, "אישור חיבור למים וביוב מתאגיד המים")
    assert "אישור חיבור לביוב" in water_step["required_documents"]


async def test_ignored_condition_changes_nothing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_read(*_: Any) -> tuple[list[FoundCondition], str]:
        return [FOUND[0].model_copy()], "claude"

    monkeypatch.setattr(conditions, "read", fake_read)
    token = await register(client)
    project = await new_project(client, token, locality_code=RAANANA)
    before = len(await requirements(client, token, project["id"]))
    await upload_permit(client, token, project["id"])
    await client.post(f"/api/v1/projects/{project['id']}/permit/check", headers=auth(token))
    [tree] = (await conditions_of(client, token, project["id"]))["conditions"]
    await client.post(
        f"/api/v1/projects/{project['id']}/permit/conditions/{tree['id']}/ignore",
        headers=auth(token),
    )
    assert len(await requirements(client, token, project["id"])) == before


def test_reading_conditions_from_permit_text() -> None:
    found = conditions_from_text(
        """היתר בנייה מספר: 20250412
        תנאים להיתר:
        1. ההיתר כפוף לכל דין.
        2. לפני תחילת עבודות יש למנות מהנדס אחראי לביקורת על הביצוע.
        3. לפני מתן תעודת גמר יש להציג אישור תאגיד המים על חיבור לביוב.
        4. התקנת מערכת סולארית לחימום מים.
        """
    )
    assert [(c.number, c.timing, c.authority_type) for c in found] == [
        ("2", ConditionTiming.before_work, AuthorityType.supervising_engineer),
        ("3", ConditionTiming.before_form4, AuthorityType.water_corporation),
        ("4", ConditionTiming.before_form4, AuthorityType.municipality),
    ]


async def test_the_authority_list_is_added_in_its_area(client: AsyncClient) -> None:
    token = await register(client)
    project = await new_project(client, token, locality_code=YEROHAM)
    reqs = await requirements(client, token, project["id"])
    developer = by_title(reqs, "התייחסות החברה המפתחת")
    assert developer["stage"] == "form4" and developer["origin"] == "city_list"
    plans = by_title(reqs, "הצהרת מתכנן השלד (טופס ה-2)")
    assert "תוכניות קונסטרוקציה בקובצי PDF" in plans["required_documents"]

    elsewhere = await new_project(client, token, locality_code=RAANANA)
    titles = {r["title"] for r in await requirements(client, token, elsewhere["id"])}
    assert "התייחסות החברה המפתחת" not in titles


async def test_what_an_authority_asks_for_joins_the_step(client: AsyncClient) -> None:
    token = await register(client)
    project = await new_project(client, token, locality_code=RAANANA)
    await deliver(
        client,
        email(
            project["inbox_address"],
            subject="בקשה להשלמת מסמכים - חיבור מים",
            TextBody="לצורך אישור החיבור יש להשלים תוכנית אינסטלציה חתומה.",
        ),
    )
    [suggestion] = await pending(client, token, project["id"])
    assert suggestion["kind"] == "request_for_info"
    assert suggestion["missing_documents"] == ["תוכנית אינסטלציה חתומה"]
    await client.post(
        f"/api/v1/projects/{project['id']}/suggestions/{suggestion['id']}/accept",
        headers=auth(token),
        json={"apply_status": False},
    )
    step = next(
        r
        for r in await requirements(client, token, project["id"])
        if r["id"] == suggestion["requirement_id"]
    )
    assert "תוכנית אינסטלציה חתומה" in step["required_documents"]
