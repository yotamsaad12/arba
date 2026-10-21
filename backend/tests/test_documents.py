import csv
import io
import zipfile
from typing import Any

from httpx import AsyncClient

from tests.conftest import auth, register
from tests.test_projects import by_title, create_project, requirements

PDF = b"%PDF-1.4\n% permit scan\n"


async def upload(
    client: AsyncClient,
    token: str,
    project_id: str,
    *,
    name: str = "היתר בנייה.pdf",
    data: bytes = PDF,
    requirement_id: str | None = None,
) -> dict[str, Any]:
    started = await client.post(
        f"/api/v1/projects/{project_id}/documents",
        headers=auth(token),
        json={
            "file_name": name,
            "content_type": "application/pdf",
            "size_bytes": len(data),
            "requirement_id": requirement_id,
        },
    )
    assert started.status_code == 201, started.text
    target = started.json()["upload"]
    put = await client.request(
        target["method"], target["url"], content=data, headers=target["headers"]
    )
    assert put.status_code == 204, put.text
    done = await client.post(
        f"/api/v1/projects/{project_id}/documents/{started.json()['document_id']}/complete",
        headers=auth(token),
    )
    assert done.status_code == 200, done.text
    return done.json()


async def test_upload_list_and_download(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    permit = by_title(await requirements(client, token, project["id"]), "היתר בנייה")
    document = await upload(client, token, project["id"], requirement_id=permit["id"])
    assert (document["uploaded_by_name"], document["size_bytes"]) == ("דנה כהן", len(PDF))

    listed = (
        await client.get(f"/api/v1/projects/{project['id']}/documents", headers=auth(token))
    ).json()
    assert [d["id"] for d in listed] == [document["id"]]

    download = await client.get(listed[0]["download_url"])
    assert download.content == PDF
    assert download.headers["x-content-type-options"] == "nosniff"
    assert "filename*=UTF-8''" in download.headers["content-disposition"]

    permit = by_title(await requirements(client, token, project["id"]), "היתר בנייה")
    assert permit["document_count"] == 1


async def test_rejects_disallowed_types_and_sizes(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    url = f"/api/v1/projects/{project['id']}/documents"
    exe = {"file_name": "virus.exe", "content_type": "application/x-msdownload", "size_bytes": 10}
    assert (await client.post(url, headers=auth(token), json=exe)).status_code == 415
    huge = {"file_name": "a.pdf", "content_type": "application/pdf", "size_bytes": 10**10}
    assert (await client.post(url, headers=auth(token), json=huge)).status_code == 413


async def test_complete_without_upload_and_tampered_links_fail(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    started = (
        await client.post(
            f"/api/v1/projects/{project['id']}/documents",
            headers=auth(token),
            json={"file_name": "a.pdf", "content_type": "application/pdf", "size_bytes": 3},
        )
    ).json()
    complete = await client.post(
        f"/api/v1/projects/{project['id']}/documents/{started['document_id']}/complete",
        headers=auth(token),
    )
    assert complete.status_code == 409

    tampered = started["upload"]["url"][:-4] + "abcd"
    assert (await client.put(tampered, content=b"x")).status_code == 403
    # An upload link can't be used to download.
    assert (await client.get(started["upload"]["url"])).status_code == 403


async def test_file_unfile_and_delete(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    permit = by_title(await requirements(client, token, project["id"]), "היתר בנייה")
    document = await upload(client, token, project["id"])
    url = f"/api/v1/projects/{project['id']}/documents/{document['id']}"

    filed = await client.patch(url, headers=auth(token), json={"requirement_id": permit["id"]})
    assert filed.json()["requirement_id"] == permit["id"]
    unfiled = await client.patch(url, headers=auth(token), json={"requirement_id": None})
    assert unfiled.json()["requirement_id"] is None

    assert (await client.delete(url, headers=auth(token))).status_code == 204
    listed = (
        await client.get(f"/api/v1/projects/{project['id']}/documents", headers=auth(token))
    ).json()
    assert listed == []


async def test_export_zip_is_organised_by_stage_and_requirement(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    permit = by_title(await requirements(client, token, project["id"]), "היתר בנייה")
    await upload(client, token, project["id"], requirement_id=permit["id"])
    await upload(client, token, project["id"], requirement_id=permit["id"])  # same name twice
    await upload(client, token, project["id"], name="צילום.pdf")

    response = await client.get(
        f"/api/v1/projects/{project['id']}/documents/export", headers=auth(token)
    )
    assert response.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = sorted(archive.namelist())
    folder = "01 לפני שמתחילים/היתר בנייה בתוקף ורשימת התנאים שבו"
    assert names == sorted(
        [
            f"{folder}/היתר בנייה.pdf",
            f"{folder}/היתר בנייה (2).pdf",
            "00 לא מתויק/צילום.pdf",
            "index.csv",
        ]
    )
    rows = list(csv.reader(io.StringIO(archive.read("index.csv").decode("utf-8-sig"))))
    assert len(rows) == 4


async def test_documents_are_private_to_project_members(client: AsyncClient) -> None:
    token = await register(client)
    project = await create_project(client, token)
    await upload(client, token, project["id"])
    stranger = await register(client, email="other@example.com")
    response = await client.get(
        f"/api/v1/projects/{project['id']}/documents", headers=auth(stranger)
    )
    assert response.status_code == 404
