"""
dashboard/oauth.py — Discord OAuth2 login flow for the Echo dashboard.

Standard Authorization Code flow:
  1. /auth/login          -> redirect to Discord's consent screen
  2. Discord redirects back to /auth/callback?code=...
  3. We exchange the code for an access token
  4. We fetch the user's identity + guild list with that token
  5. We store a signed session cookie so the dashboard remembers them

No passwords are ever handled by Echo — Discord does all the auth.
"""

import os
import time
import secrets
import aiohttp
from itsdangerous import URLSafeTimedSerializer, BadSignature

DISCORD_API = "https://discord.com/api/v10"
OAUTH_SCOPES = "identify guilds"

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("DASHBOARD_REDIRECT_URI", "http://localhost:8080/auth/callback")
SESSION_SECRET = os.getenv("DASHBOARD_SESSION_SECRET") or secrets.token_hex(32)

_serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="Echo-dashboard-session")

SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def build_authorize_url(state: str) -> str:
    from urllib.parse import urlencode
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": OAUTH_SCOPES,
        "state": state,
        "prompt": "none",
    }
    return f"{DISCORD_API}/oauth2/authorize?{urlencode(params)}"


async def exchange_code(code: str) -> dict | None:
    """Trade an OAuth2 authorization code for an access token."""
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{DISCORD_API}/oauth2/token", data=data, headers=headers) as r:
            if r.status != 200:
                return None
            return await r.json()


async def fetch_user(access_token: str) -> dict | None:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{DISCORD_API}/users/@me", headers=headers) as r:
            if r.status != 200:
                return None
            return await r.json()


async def fetch_user_guilds(access_token: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{DISCORD_API}/users/@me/guilds", headers=headers) as r:
            if r.status != 200:
                return []
            return await r.json()


def create_session_token(user: dict) -> str:
    """Sign a session payload for the browser cookie."""
    payload = {
        "id": user["id"],
        "username": user.get("username"),
        "discriminator": user.get("discriminator", "0"),
        "avatar": user.get("avatar"),
        "issued_at": int(time.time()),
    }
    return _serializer.dumps(payload)


def read_session_token(token: str) -> dict | None:
    try:
        return _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None
    except Exception:
        return None


def avatar_url(user_id: str, avatar_hash: str | None) -> str:
    if avatar_hash:
        ext = "gif" if avatar_hash.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size=128"
    # Default avatar fallback
    default_index = (int(user_id) >> 22) % 6
    return f"https://cdn.discordapp.com/embed/avatars/{default_index}.png"
