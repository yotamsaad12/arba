from typing import Any

from httpx import AsyncClient

from tests.conftest import auth
from tests.test_documents import upload
from tests.test_inbox import deliver, email, inbox, setup_project
from tests.test_projects import by_title, requirements

WATER_APPROVAL = "אישור חיבור למים וביוב מתאגיד המים"
MAMAD_REBAR = 'בדיקת ברזל ותבניות של הממ"ד לפני יציקה'


def hfc_request(to: str, **extra: Any) -> dict[str, Any]:
    return email(
        to,
        provider_id="pm-hfc",
        message_id="<hfc@oref.org.il>",
        sender="mamad@oref.org.il",
        subject='בקשה להשלמת מסמכים - ממ"ד',
        TextBody="לצורך מתן האישור נדרש להשלים: צילום ברזל לפני יציקה.",
        **extra,
    )


async def pending(client: AsyncClient, token: str, project_id: str) -> list[dict[str, Any]]:
    response = await client.get(f"/api/v1/projects/{project_id}/suggestions", headers=auth(token))
    assert response.status_code == 200, response.text
    return response.json()


async def accept(
    client: AsyncClient, token: str, project_id: str, suggestion_id: str, **body: Any
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/projects/{project_id}/suggestions/{suggestion_id}/accept",
        headers=auth(token),
        json=body,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_incoming_approval_gets_a_filing_suggestion(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    await deliver(client, email(project["inbox_address"]))

    [suggestion] = await pending(client, token, project["id"])
    assert suggestion["target"] == "thread"
    assert suggestion["requirement_title"] == WATER_APPROVAL
    assert (suggestion["kind"], suggestion["suggested_status"]) == ("approval", "done")
    assert suggestion["file_count"] == 1
    assert suggestion["source"] == "rules"


async def test_accepting_files_the_thread_and_reports_a_blocked_status(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    await deliver(client, email(project["inbox_address"]))
    [suggestion] = await pending(client, token, project["id"])

    result = await accept(client, token, project["id"], suggestion["id"])
    # Filed, but "done" needs the plumbing requirements first, so the status is left alone.
    assert (result["status_applied"], result["status_error"]) == (False, "dependencies_not_done")
    thread = (await inbox(client, token, project["id"]))[0]
    assert thread["requirement_title"] == WATER_APPROVAL
    assert await pending(client, token, project["id"]) == []


async def test_request_for_documents_marks_requirement_needs_fix(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    await deliver(client, hfc_request(project["inbox_address"]))
    [suggestion] = await pending(client, token, project["id"])
    assert suggestion["requirement_title"] == MAMAD_REBAR
    assert (suggestion["kind"], suggestion["suggested_status"]) == ("request_for_info", "needs_fix")

    result = await accept(client, token, project["id"], suggestion["id"])
    assert result["status_applied"] is True
    rebar = by_title(await requirements(client, token, project["id"]), MAMAD_REBAR)
    assert rebar["status"] == "needs_fix"


async def test_person_can_choose_a_different_requirement(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    await deliver(client, email(project["inbox_address"]))
    [suggestion] = await pending(client, token, project["id"])
    sewage = by_title(await requirements(client, token, project["id"]), "ביוב וניקוז")

    result = await accept(
        client,
        token,
        project["id"],
        suggestion["id"],
        requirement_id=sewage["id"],
        apply_status=False,
    )
    assert (result["requirement_id"], result["status_applied"]) == (sewage["id"], False)
    sewage = by_title(await requirements(client, token, project["id"]), "ביוב וניקוז")
    assert sewage["document_count"] == 1


async def test_dismiss_and_manual_filing_clear_the_suggestion(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    await deliver(client, email(project["inbox_address"]))
    await deliver(client, hfc_request(project["inbox_address"]))
    water, hfc = sorted(await pending(client, token, project["id"]), key=lambda s: s["title"])

    dismissed = await client.post(
        f"/api/v1/projects/{project['id']}/suggestions/{water['id']}/dismiss", headers=auth(token)
    )
    assert dismissed.status_code == 204

    permit = by_title(await requirements(client, token, project["id"]), "היתר בנייה")
    await client.patch(
        f"/api/v1/projects/{project['id']}/threads/{hfc['thread_id']}",
        headers=auth(token),
        json={"requirement_id": permit["id"]},
    )
    assert await pending(client, token, project["id"]) == []

    again = await client.post(
        f"/api/v1/projects/{project['id']}/suggestions/{water['id']}/accept",
        headers=auth(token),
        json={},
    )
    assert again.status_code == 409


async def test_a_reply_replaces_the_threads_open_suggestion(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    to = project["inbox_address"]
    await deliver(client, email(to))
    await deliver(client, email(to, provider_id="pm-2", message_id="<m2@x>",
                                in_reply_to="<m1@water.co.il>"))  # fmt: skip
    assert len(await pending(client, token, project["id"])) == 1


async def test_unfiled_upload_gets_a_suggestion(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    document = await upload(client, token, project["id"], name='אישור ממ"ד פיקוד העורף.pdf')
    [suggestion] = await pending(client, token, project["id"])
    assert (suggestion["target"], suggestion["document_id"]) == ("document", document["id"])
    assert suggestion["requirement_title"] is not None
    # Named "אישור…": treated as a certificate.
    assert (suggestion["kind"], suggestion["suggested_status"]) == ("approval", "done")
    assert suggestion["summary"] == 'קובץ חדש: אישור ממ"ד פיקוד העורף'

    await accept(client, token, project["id"], suggestion["id"])
    docs = (
        await client.get(f"/api/v1/projects/{project['id']}/documents", headers=auth(token))
    ).json()
    assert docs[0]["requirement_id"] == suggestion["requirement_id"]


async def test_upload_filed_on_purpose_gets_no_suggestion(client: AsyncClient) -> None:
    token, project = await setup_project(client)
    permit = by_title(await requirements(client, token, project["id"]), "היתר בנייה")
    await upload(client, token, project["id"], requirement_id=permit["id"])
    assert await pending(client, token, project["id"]) == []
