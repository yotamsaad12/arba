from datetime import date, timedelta
from typing import Any

from httpx import AsyncClient

from app.modules.permits.extraction import fields_from_text
from tests.conftest import auth, register
from tests.test_documents import upload
from tests.test_inbox import deliver, email
from tests.test_projects import by_title, requirements
from tests.test_suggestions import pending

RAANANA, KFAR_SHMARYAHU, ARIEL = 8700, 267, 3570
RAANANA_COMMITTEE = "הוועדה המקומית לתכנון ובנייה רעננה"


async def template_id(client: AsyncClient, token: str) -> str:
    templates = (await client.get("/api/v1/templates", headers=auth(token))).json()
    return templates[0]["id"]


async def new_project(client: AsyncClient, token: str, **fields: Any) -> dict[str, Any]:
    body = {"name": "בית בבדיקה", "template_id": await template_id(client, token), **fields}
    response = await client.post("/api/v1/projects", headers=auth(token), json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def permit(
    client: AsyncClient, token: str, project_id: str, action: str = ""
) -> dict[str, Any]:
    url = f"/api/v1/projects/{project_id}/permit" + (f"/{action}" if action else "")
    response = await (
        client.post(url, headers=auth(token)) if action else client.get(url, headers=auth(token))
    )
    assert response.status_code == 200, response.text
    return response.json()


async def upload_permit(client: AsyncClient, token: str, project_id: str) -> None:
    permit_req = by_title(await requirements(client, token, project_id), "היתר בנייה")
    await upload(client, token, project_id, name="היתר.pdf", requirement_id=permit_req["id"])


def checks(result: dict[str, Any]) -> dict[str, bool | None]:
    return {c["check"]: c["ok"] for c in result["checks"]}


# --- directory ------------------------------------------------------------------------


async def test_locality_search_knows_the_committee(client: AsyncClient) -> None:
    token = await register(client)
    found = (
        await client.get("/api/v1/directory/localities", params={"q": "רעננה"}, headers=auth(token))
    ).json()
    assert (found[0]["code"], found[0]["committee"], found[0]["committee_source"]) == (
        RAANANA,
        "רעננה",
        "planning_map",
    )
    # Kfar Shmaryahu is planned by Herzliya's regional committee.
    found = (
        await client.get(
            "/api/v1/directory/localities", params={"q": "כפר שמריהו"}, headers=auth(token)
        )
    ).json()
    assert found[0]["committee"] == "הרצליה"


async def test_project_in_a_locality_gets_its_authorities(client: AsyncClient) -> None:
    token = await register(client)
    project = await new_project(client, token, locality_code=RAANANA)
    assert (project["municipality"], project["permit_status"]) == ("רעננה", "pending_verification")
    authorities = (
        await client.get(f"/api/v1/projects/{project['id']}/authorities", headers=auth(token))
    ).json()
    assert RAANANA_COMMITTEE in {a["name"] for a in authorities}


async def test_filed_mail_teaches_the_directory(client: AsyncClient) -> None:
    token = await register(client)
    project = await new_project(client, token, locality_code=RAANANA)
    await deliver(client, email(project["inbox_address"]))
    [suggestion] = await pending(client, token, project["id"])
    await client.post(
        f"/api/v1/projects/{project['id']}/suggestions/{suggestion['id']}/accept",
        headers=auth(token),
        json={"apply_status": False},
    )
    authorities = (
        await client.get(f"/api/v1/projects/{project['id']}/authorities", headers=auth(token))
    ).json()
    water = next(a for a in authorities if a["type"] == "water_corporation")
    assert [(c["email"], c["source"]) for c in water["contacts"]] == [
        ("water@water.co.il", "learned")
    ]


# --- permit ---------------------------------------------------------------------------


async def test_project_opens_pending_until_the_permit_checks_out(client: AsyncClient) -> None:
    token = await register(client)
    project = await new_project(
        client,
        token,
        locality_code=RAANANA,
        permit_number="20250123",
        permit_issue_date=(date.today() - timedelta(days=60)).isoformat(),
        permit_committee=RAANANA_COMMITTEE,
    )
    result = await permit(client, token, project["id"])
    assert result["status"] == "pending_verification"
    assert checks(result)["document"] is False

    await upload_permit(client, token, project["id"])
    result = await permit(client, token, project["id"], "check")
    assert result["status"] == "document_checked", result["checks"]
    assert checks(result) == {
        "document": True, "number": True, "validity": True, "committee": True, "location": True
    }  # fmt: skip
    permit_req = by_title(await requirements(client, token, project["id"]), "היתר בנייה")
    assert permit_req["status"] == "done"


async def test_permit_from_the_wrong_committee_needs_attention(client: AsyncClient) -> None:
    token = await register(client)
    project = await new_project(
        client,
        token,
        locality_code=RAANANA,
        permit_number="1",
        permit_issue_date=date.today().isoformat(),
        permit_committee="הוועדה המקומית לתכנון ובנייה חיפה",
    )
    await upload_permit(client, token, project["id"])
    result = await permit(client, token, project["id"], "check")
    assert result["status"] == "needs_attention"
    assert checks(result)["committee"] is False


async def test_expired_permit_needs_attention(client: AsyncClient) -> None:
    token = await register(client)
    project = await new_project(
        client,
        token,
        locality_code=ARIEL,
        permit_number="7",
        permit_valid_until=(date.today() - timedelta(days=1)).isoformat(),
    )
    await upload_permit(client, token, project["id"])
    result = await permit(client, token, project["id"], "check")
    assert (result["status"], checks(result)["validity"]) == ("needs_attention", False)


async def test_committee_confirmation_needs_the_document(client: AsyncClient) -> None:
    token = await register(client)
    project = await new_project(client, token, locality_code=KFAR_SHMARYAHU)
    response = await client.post(
        f"/api/v1/projects/{project['id']}/permit/confirm", headers=auth(token)
    )
    assert response.json()["error"]["code"] == "permit_document_missing"

    await upload_permit(client, token, project["id"])
    result = await permit(client, token, project["id"], "confirm")
    assert result["status"] == "committee_confirmed" and result["confirmed_at"]


async def test_editing_permit_details_rechecks(client: AsyncClient) -> None:
    token = await register(client)
    project = await new_project(client, token, locality_code=RAANANA)
    await upload_permit(client, token, project["id"])
    response = await client.patch(
        f"/api/v1/projects/{project['id']}/permit",
        headers=auth(token),
        json={"permit_number": "555", "permit_issue_date": date.today().isoformat()},
    )
    assert response.json()["status"] == "document_checked"


def test_reading_permit_text() -> None:
    text = """
    הוועדה המקומית לתכנון ובנייה רעננה
    היתר בנייה מספר: 20240567
    מספר בקשה: 1018273645
    גוש: 6587 חלקה: 112
    תאריך הפקת ההיתר: 14/03/2026
    """
    fields = fields_from_text(text)
    assert fields.is_permit
    assert (fields.permit_number, fields.request_number) == ("20240567", "1018273645")
    assert (fields.gush, fields.helka) == ("6587", "112")
    assert fields.issue_date == date(2026, 3, 14)
    assert fields.committee and "רעננה" in fields.committee


async def test_extract_rejects_non_permits(client: AsyncClient) -> None:
    from app.scripts.send_test_email import sample_pdf

    token = await register(client)
    response = await client.post(
        "/api/v1/permits/extract",
        headers=auth(token),
        files={"file": ("x.pdf", sample_pdf("hello"), "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["fields"]["is_permit"] is False
    not_pdf = await client.post(
        "/api/v1/permits/extract",
        headers=auth(token),
        files={"file": ("x.txt", b"hi", "text/plain")},
    )
    assert not_pdf.status_code == 415


def test_reading_permit_text_with_values_before_labels() -> None:
    # How pypdf extracts a right-to-left permit: numbers come out before their labels.
    text = """
    הוועדה המקומית לתכנון ובנייה רעננה
    20250412 :היתר בנייה מספר
    1022334455 :מספר בקשה
    112 : חלקה6587 :גוש
    14/03/2026 :תאריך הפקת ההיתר
    """
    fields = fields_from_text(text)
    assert (fields.permit_number, fields.request_number) == ("20250412", "1022334455")
    assert (fields.gush, fields.helka) == ("6587", "112")
    assert fields.issue_date == date(2026, 3, 14)
