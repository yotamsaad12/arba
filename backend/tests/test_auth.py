from httpx import AsyncClient
from sqlalchemy import text

from app.db.session import engine
from tests.conftest import auth, register


async def test_register_creates_user_and_private_org(client: AsyncClient) -> None:
    token = await register(client)
    me = (await client.get("/api/v1/auth/me", headers=auth(token))).json()
    assert me["email"] == "dana@example.com"
    assert [(o["type"], o["role"]) for o in me["organizations"]] == [("private", "owner")]


async def test_email_is_unique_case_insensitively(client: AsyncClient) -> None:
    await register(client)
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "x",
            "email": "DANA@example.com",
            "password": "correct-horse",
            "client_type": "private",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


async def test_business_needs_organization_name(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "x",
            "email": "b@example.com",
            "password": "12345678",
            "client_type": "business",
        },
    )
    assert response.status_code == 422


async def test_login_with_wrong_password_fails(client: AsyncClient) -> None:
    await register(client)
    response = await client.post(
        "/api/v1/auth/login", json={"email": "dana@example.com", "password": "nope-nope"}
    )
    assert response.status_code == 401


async def test_me_requires_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    bad = await client.get("/api/v1/auth/me", headers=auth("garbage"))
    assert bad.status_code == 401


async def test_web_refresh_uses_cookie_and_rotates(client: AsyncClient) -> None:
    await register(client)
    first_cookie = client.cookies.get("arba_refresh")
    assert first_cookie

    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] is None  # web clients never see it
    assert client.cookies.get("arba_refresh") != first_cookie


async def mobile_login(client: AsyncClient) -> str:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "dana@example.com", "password": "correct-horse", "client": "mobile"},
    )
    return login.json()["refresh_token"]


async def test_two_tabs_refreshing_at_once_both_succeed(client: AsyncClient) -> None:
    await register(client)
    old = await mobile_login(client)
    body = {"refresh_token": old, "client": "mobile"}
    first = await client.post("/api/v1/auth/refresh", json=body)
    second = await client.post("/api/v1/auth/refresh", json=body)
    assert (first.status_code, second.status_code) == (200, 200)


async def test_reused_refresh_token_ends_all_sessions(client: AsyncClient) -> None:
    await register(client)
    old = await mobile_login(client)
    rotated = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old, "client": "mobile"}
    )
    new = rotated.json()["refresh_token"]
    # Move the rotation outside the grace window.
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE refresh_tokens SET rotated_at = rotated_at - interval '1 minute'")
        )

    # Someone replays the old token: it fails, and the new one is revoked too.
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old, "client": "mobile"}
    )
    assert replay.status_code == 401
    after = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": new, "client": "mobile"}
    )
    assert after.status_code == 401


async def test_logout_revokes_cookie_token(client: AsyncClient) -> None:
    await register(client)
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
