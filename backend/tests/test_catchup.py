from datetime import date, timedelta
from email.message import EmailMessage
from typing import Any

from httpx import AsyncClient

from app.email.parsing import parse_rfc822
from app.modules.catchup.search import MailSearch, _street
from tests.conftest import auth, register
from tests.test_permits_directory import RAANANA, new_project
from tests.test_projects import requirements


async def raanana_project(client: AsyncClient, token: str) -> dict[str, Any]:
    return await new_project(
        client,
        token,
        locality_code=RAANANA,
        address="רחוב אחוזה 120, רעננה",
        gush="6587",
        helka="112",
        permit_number="20250412",
        permit_issue_date=(date.today() - timedelta(days=420)).isoformat(),
    )


async def scan(client: AsyncClient, token: str, project_id: str) -> dict[str, Any]:
    started = await client.post(f"/api/v1/projects/{project_id}/mailbox/scans", headers=auth(token))
    assert started.status_code == 201, started.text
    # The scan runs as a background task, which the test client awaits.
    response = await client.get(
        f"/api/v1/projects/{project_id}/mailbox/scans/{started.json()['id']}", headers=auth(token)
    )
    return response.json()


async def report(client: AsyncClient, token: str, project_id: str) -> dict[str, Any]:
    response = await client.get(
        f"/api/v1/projects/{project_id}/catch-up/report", headers=auth(token)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_search_names_the_project_and_its_authorities(client: AsyncClient) -> None:
    token = await register(client)
    project = await raanana_project(client, token)
    connect = (
        await client.get(f"/api/v1/projects/{project['id']}/mailbox/connect", headers=auth(token))
    ).json()
    assert connect == {"provider": "simulator", "url": None}

    result = await scan(client, token, project["id"])
    query = result["query"]
    for term in ("20250412", '"גוש 6587"', '"אחוזה 120"', "from:raanana.muni.il"):
        assert term in query
    assert "myvisit" not in query and "after:" in query


async def test_scan_imports_project_mail_only_and_announces_once(client: AsyncClient) -> None:
    token = await register(client)
    project = await raanana_project(client, token)
    result = await scan(client, token, project["id"])
    assert result["status"] == "done", result["error"]
    # Eight mails in the mailbox; the property-tax bill and the shop's offer stay out.
    assert (result["messages_found"], result["messages_imported"], result["files_imported"]) == (
        6,
        6,
        5,
    )

    threads = (
        await client.get(f"/api/v1/projects/{project['id']}/inbox", headers=auth(token))
    ).json()
    subjects = " ".join(t["subject"] for t in threads)
    assert "ארנונה" not in subjects and "מבצע" not in subjects
    sent = next(t for t in threads if "תיק תוכניות" in t["subject"])
    assert sent["counterparty_email"] == "architect@studio.example.co.il"

    suggestions = (
        await client.get(f"/api/v1/projects/{project['id']}/suggestions", headers=auth(token))
    ).json()
    assert len(suggestions) == 6
    notifications = (await client.get("/api/v1/me/notifications", headers=auth(token))).json()
    assert [n["kind"] for n in notifications["items"]] == ["import_finished"]

    # Scanning again finds the same mail and imports nothing twice.
    again = await scan(client, token, project["id"])
    assert (again["messages_found"], again["messages_imported"]) == (6, 0)


async def test_catch_up_then_report_what_is_missing(client: AsyncClient) -> None:
    token = await register(client)
    project = await raanana_project(client, token)
    done = await client.post(
        f"/api/v1/projects/{project['id']}/catch-up",
        headers=auth(token),
        json={"stage": "skeleton"},
    )
    assert done.status_code == 200 and done.json()["marked_done"] > 5
    reqs = await requirements(client, token, project["id"])
    pre = [r for r in reqs if r["stage"] in ("pre", "foundations") and not r["optional"]]
    assert all(r["status"] == "done" for r in pre)

    before = await report(client, token, project["id"])
    # Nothing gathered yet; the steps already done are all missing their documents.
    assert (before["state"], before["found"]) == ("empty", [])
    missing_before = {i["requirement_id"] for i in before["missing"]}
    assert {r["id"] for r in pre if r["required_documents"]} <= missing_before

    await scan(client, token, project["id"])
    response = await client.post(
        f"/api/v1/projects/{project['id']}/suggestions/accept-all", headers=auth(token), json={}
    )
    assert response.status_code == 200
    accepted = response.json()
    assert accepted["accepted"] + accepted["left"] == 6

    after = await report(client, token, project["id"])
    assert after["pending_suggestions"] == accepted["left"]
    found = {i["requirement_id"] for i in after["found"] if i["documents"]}
    # What the mailbox held now covers steps that were missing documents before.
    assert found & missing_before
    assert len(after["missing"]) < len(before["missing"])


async def test_unknown_stage_is_refused(client: AsyncClient) -> None:
    token = await register(client)
    project = await raanana_project(client, token)
    response = await client.post(
        f"/api/v1/projects/{project['id']}/catch-up", headers=auth(token), json={"stage": "x"}
    )
    assert response.json()["error"]["code"] == "unknown_stage"


def test_raw_mail_with_hebrew_and_attachment() -> None:
    msg = EmailMessage()
    msg["From"] = "רישוי בנייה <rishui@raanana.muni.il>"
    msg["To"] = "dana@example.com"
    msg["Subject"] = "היתר בנייה מס' 20250412"
    msg["Message-ID"] = "<abc@raanana.muni.il>"
    msg["Date"] = "Sun, 14 Jun 2026 09:30:00 +0300"
    msg.set_content("מצורף ההיתר. גוש: 6587")
    msg.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf", filename="היתר.pdf")
    email = parse_rfc822(msg.as_bytes(), "x")
    assert (email.from_email, email.from_name) == ("rishui@raanana.muni.il", "רישוי בנייה")
    assert email.subject == "היתר בנייה מס' 20250412" and email.message_id == "abc@raanana.muni.il"
    assert [a.name for a in email.attachments] == ["היתר.pdf"]

    search = MailSearch(phrases=["גוש 6587"], domains=[], keywords=[])
    assert search.matches(email)
    assert not MailSearch(phrases=["גוש 1111"]).matches(email)
    # Authority mail counts only when it is about building.
    by_domain = MailSearch(domains=["muni.il"], keywords=["ארנונה"])
    assert not by_domain.matches(email)


def test_street_from_address() -> None:
    assert _street("רחוב אחוזה 120, רעננה") == "אחוזה 120"
    assert _street("רעננה") is None
