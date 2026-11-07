from app.config import settings
from app.services.users import ensure_bootstrap_admin


async def login(client, email, password):
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    return response


async def auth_headers(client, email, password):
    response = await login(client, email, password)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_viewer_can_read_but_not_write(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    await ensure_bootstrap_admin()
    admin = await auth_headers(client, settings.admin_email, settings.admin_password)

    created = await client.post(
        "/api/users",
        headers=admin,
        json={
            "email": "izle@sirket.com",
            "name": "İzleyici",
            "password": "gizli-sifre-1",
            "role": "viewer",
        },
    )
    assert created.status_code == 201

    viewer = await auth_headers(client, "izle@sirket.com", "gizli-sifre-1")
    assert (await client.get("/api/monitors", headers=viewer)).status_code == 200
    assert (await client.get("/api/dashboard", headers=viewer)).status_code == 200
    assert (await client.get("/api/channels", headers=viewer)).status_code == 403
    write = await client.post(
        "/api/monitors",
        headers=viewer,
        json={"name": "Yasak", "url": "https://example.com/health"},
    )
    assert write.status_code == 403


async def test_last_admin_cannot_be_removed(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    await ensure_bootstrap_admin()
    admin = await auth_headers(client, settings.admin_email, settings.admin_password)
    me = (await client.get("/api/auth/me", headers=admin)).json()
    assert me["role"] == "admin"

    users = (await client.get("/api/users", headers=admin)).json()
    admin_id = next(user["id"] for user in users if user["email"] == settings.admin_email)

    demote = await client.patch(f"/api/users/{admin_id}", headers=admin, json={"role": "viewer"})
    assert demote.status_code == 400
    remove = await client.delete(f"/api/users/{admin_id}", headers=admin)
    assert remove.status_code == 400


async def test_deactivated_user_loses_access(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    await ensure_bootstrap_admin()
    admin = await auth_headers(client, settings.admin_email, settings.admin_password)
    created = await client.post(
        "/api/users",
        headers=admin,
        json={
            "email": "pasif@sirket.com",
            "name": "Pasif",
            "password": "gizli-sifre-2",
            "role": "admin",
        },
    )
    user_id = created.json()["id"]
    viewer = await auth_headers(client, "pasif@sirket.com", "gizli-sifre-2")

    await client.patch(f"/api/users/{user_id}", headers=admin, json={"active": False})
    assert (await login(client, "pasif@sirket.com", "gizli-sifre-2")).status_code == 401
    assert (await client.get("/api/monitors", headers=viewer)).status_code == 401


async def test_wrong_password_is_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    await ensure_bootstrap_admin()
    response = await login(client, settings.admin_email, "yanlis")
    assert response.status_code == 401
