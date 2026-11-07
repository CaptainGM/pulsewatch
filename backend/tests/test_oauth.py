from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.api.routes import auth as auth_routes
from app.config import settings
from app.security import decode_access_token


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client")
    monkeypatch.setattr(settings, "google_client_secret", "test-secret")
    monkeypatch.setattr(settings, "public_url", "http://testserver")
    monkeypatch.setattr(settings, "oauth_allowed_domains", "")
    monkeypatch.setattr(settings, "oauth_auto_create", False)
    profile = {"email": "ali@sirket.com", "email_verified": True, "name": "Ali Yılmaz"}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == settings.google_token_url:
            return httpx.Response(200, json={"access_token": "google-access"})
        if str(request.url) == settings.google_userinfo_url:
            assert request.headers["Authorization"] == "Bearer google-access"
            return httpx.Response(200, json=profile)
        return httpx.Response(404)

    def fake_client():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(auth_routes, "_http_client", fake_client)
    return profile


def fragment_of(location: str) -> dict:
    return parse_qs(urlparse(location).fragment)


async def start_flow(client):
    response = await client.get("/api/auth/google/login", follow_redirects=False)
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query["state"][0]


async def test_google_button_hidden_without_credentials(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "google_client_secret", "")
    assert (await client.get("/api/auth/config")).json()["google"] is False
    assert (await client.get("/api/auth/google/login", follow_redirects=False)).status_code == 404


async def test_login_redirect_carries_client_and_signed_state(client, google):
    response = await client.get("/api/auth/google/login", follow_redirects=False)
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["client_id"] == ["test-client"]
    assert query["redirect_uri"] == ["http://testserver/api/auth/google/callback"]
    assert query["response_type"] == ["code"]


async def test_callback_rejects_forged_state(client, google):
    response = await client.get(
        "/api/auth/google/callback?code=abc&state=forged", follow_redirects=False
    )
    assert fragment_of(response.headers["location"])["oauth_error"] == ["state"]


async def test_unknown_user_is_rejected_by_default(client, google):
    state = await start_flow(client)
    response = await client.get(
        f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False
    )
    assert fragment_of(response.headers["location"])["oauth_error"] == ["not_registered"]


async def test_unverified_email_is_rejected(client, google, monkeypatch):
    google["email_verified"] = False
    state = await start_flow(client)
    response = await client.get(
        f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False
    )
    assert fragment_of(response.headers["location"])["oauth_error"] == ["unverified"]


async def test_domain_allowlist(client, google, monkeypatch):
    monkeypatch.setattr(settings, "oauth_allowed_domains", "baska.com")
    state = await start_flow(client)
    response = await client.get(
        f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False
    )
    assert fragment_of(response.headers["location"])["oauth_error"] == ["domain"]


async def test_auto_create_gives_viewer_only(client, google, monkeypatch):
    monkeypatch.setattr(settings, "oauth_auto_create", True)
    state = await start_flow(client)
    response = await client.get(
        f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False
    )
    token = fragment_of(response.headers["location"])["oauth_token"][0]
    payload = decode_access_token(token)
    assert payload["sub"] == "ali@sirket.com"
    assert payload["role"] == "viewer"
