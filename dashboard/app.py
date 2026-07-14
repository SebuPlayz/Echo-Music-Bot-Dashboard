"""
Dashboard backend. Runs in the same process as the bot, sharing
bot.db and bot.lavalink directly, so play/pause/skip/queue actions
from the website take effect immediately in the actual voice call.
"""

import os
import secrets
import asyncio
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard import oauth
from config import Config

BASE_DIR = Path(__file__).parent
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_dashboard(bot) -> FastAPI:
    app = FastAPI(title="Echo Dashboard", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    # Track connected dashboard clients per guild so we can push live
    # player updates (song changed, paused, queue updated, etc.)
    app.state.ws_clients: dict[int, set[WebSocket]] = {}
    app.state.oauth_states: set[str] = set()
    # Cache of {discord_user_id: {"guild_ids": set(...), "fetched_at": float}}
    # populated at login so /api/guilds doesn't re-hit Discord's API
    # on every page load.
    app.state.guild_cache: dict[str, dict] = {}

    # ── Helpers ──────────────────────────────────────────────────

    def get_session(request: Request) -> dict | None:
        token = request.cookies.get("Echo_session")
        if not token:
            return None
        return oauth.read_session_token(token)

    def require_session(request: Request) -> dict | None:
        session = get_session(request)
        return session

    async def member_permission_level(guild, user_id: int) -> str | None:
        """Returns 'owner' | 'manager' | 'member' | None (not in guild).
        Falls back to fetch_member() if not cached locally."""
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except Exception:
                return None
        if guild.owner_id == user_id or user_id in bot.owner_ids:
            return "owner"
        if member.guild_permissions.manage_guild:
            return "manager"
        return "member"

    def _track_thumbnail(track) -> str | None:
        """Resolve a thumbnail the same way the Discord embed does,
        so both stay in sync. Falls back locally if the cog isn't loaded."""
        if not track:
            return None
        music_cog = bot.get_cog("Music")
        if music_cog and hasattr(music_cog, "_get_thumbnail"):
            try:
                thumb = music_cog._get_thumbnail(track)
                if thumb:
                    return thumb
            except Exception:
                pass
        artwork = getattr(track, "artwork_url", None)
        if artwork:
            return artwork
        try:
            source = (getattr(track, "source_name", "") or "").lower()
            uri = (track.uri or "").lower()
            if "youtube" in source or "youtube" in uri or "youtu.be" in uri:
                return f"https://img.youtube.com/vi/{track.identifier}/hqdefault.jpg"
        except Exception:
            pass
        return None

    def player_to_dict(guild_id: int) -> dict:
        """Serialize the current lavalink player state for JSON/WebSocket."""
        lavalink = getattr(bot, "lavalink", None)
        if not lavalink:
            return {"connected": False}
        player = lavalink.player_manager.get(guild_id)
        if not player or not player.is_connected:
            return {"connected": False}

        music_cog = bot.get_cog("Music")
        current = player.current
        queue = []
        for i, track in enumerate(player.queue[:25]):
            queue.append({
                "index": i,
                "title": track.title,
                "author": track.author,
                "duration": track.duration,
                "uri": track.uri,
                "requester": track.requester,
                "thumbnail": _track_thumbnail(track),
            })

        return {
            "connected": True,
            "paused": player.paused,
            "volume": player.volume,
            "loop": bool(getattr(player, "loop", False)),
            "autoplay": bool(music_cog.autoplay_states.get(guild_id, False)) if music_cog else False,
            "position": player.position if current else 0,
            "current": {
                "title": current.title,
                "author": current.author,
                "duration": current.duration,
                "uri": current.uri,
                "requester": current.requester,
                "identifier": current.identifier,
                "thumbnail": _track_thumbnail(current),
            } if current else None,
            "queue": queue,
            "queue_length": len(player.queue),
        }

    async def broadcast_player_update(guild_id: int):
        clients = app.state.ws_clients.get(guild_id)
        if not clients:
            return
        payload = {"type": "player_update", "data": player_to_dict(guild_id)}
        dead = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)

    # Expose the broadcaster so cogs/music.py can call it after
    # play/pause/skip/etc so the dashboard updates in real time
    # without the browser needing to poll.
    bot.dashboard_broadcast = broadcast_player_update

    # ── Auth routes ──────────────────────────────────────────────

    @app.get("/auth/login")
    async def auth_login():
        state = secrets.token_urlsafe(24)
        app.state.oauth_states.add(state)
        return RedirectResponse(oauth.build_authorize_url(state))

    @app.get("/auth/callback")
    async def auth_callback(request: Request, code: str = None, state: str = None, error: str = None):
        if error or not code:
            return RedirectResponse("/?error=login_failed")

        if state not in app.state.oauth_states:
            return RedirectResponse("/?error=invalid_state")
        app.state.oauth_states.discard(state)

        token_data = await oauth.exchange_code(code)
        if not token_data:
            return RedirectResponse("/?error=token_exchange_failed")

        user = await oauth.fetch_user(token_data["access_token"])
        if not user:
            return RedirectResponse("/?error=user_fetch_failed")

        session_token = oauth.create_session_token(user)

        # Cache the user's guild list briefly so /api/guilds doesn't
        # need to re-hit Discord's API on every page load.
        guilds = await oauth.fetch_user_guilds(token_data["access_token"])
        app.state.guild_cache[user["id"]] = {
            "guilds": guilds,
            "fetched_at": asyncio.get_event_loop().time(),
        }

        resp = RedirectResponse("/dashboard")
        resp.set_cookie(
            "Echo_session", session_token,
            max_age=oauth.SESSION_MAX_AGE, httponly=True, samesite="lax"
        )
        return resp

    @app.get("/auth/logout")
    async def auth_logout():
        resp = RedirectResponse("/")
        resp.delete_cookie("Echo_session")
        return resp

    # ── Page routes ──────────────────────────────────────────────

    def _bot_avatar_url() -> str:
        """Return the bot's Discord CDN avatar URL, or fallback to static."""
        user = getattr(bot, "user", None)
        if user and user.avatar:
            return str(user.avatar.url)
        if user and user.id:
            return f"https://cdn.discordapp.com/embed/avatars/0.png"
        return "/static/Echo-avatar.png"

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        session = get_session(request)
        return templates.TemplateResponse("index.html", {
            "request": request,
            "session": session,
            "bot_name": getattr(bot, "user", None) and bot.user.name or "Echo",
            "bot_id": getattr(bot, "user", None) and bot.user.id or None,
            "bot_avatar": _bot_avatar_url(),
            "guild_count": len(bot.guilds),
            "support_server": Config.SUPPORT_SERVER,
        })

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_home(request: Request):
        session = require_session(request)
        if not session:
            return RedirectResponse("/?login_required=1")
        return templates.TemplateResponse("guilds.html", {
            "request": request,
            "session": session,
            "avatar": oauth.avatar_url(session["id"], session.get("avatar")),
            "bot_avatar": _bot_avatar_url(),
            "bot_name": getattr(bot, "user", None) and bot.user.name or "Echo",
        })

    @app.get("/dashboard/{guild_id}", response_class=HTMLResponse)
    async def dashboard_guild(request: Request, guild_id: int):
        session = require_session(request)
        if not session:
            return RedirectResponse("/?login_required=1")
        guild = bot.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail="Bot is not in that server")

        level = await member_permission_level(guild, int(session["id"]))
        if level is None:
            raise HTTPException(status_code=403, detail="You are not a member of that server")

        return templates.TemplateResponse("player.html", {
            "request": request,
            "session": session,
            "avatar": oauth.avatar_url(session["id"], session.get("avatar")),
            "bot_avatar": _bot_avatar_url(),
            "bot_name": getattr(bot, "user", None) and bot.user.name or "Echo",
            "guild": {"id": str(guild.id), "name": guild.name,
                      "icon": guild.icon.url if guild.icon else None},
            "permission_level": level,
        })

    @app.get("/status", response_class=HTMLResponse)
    async def status_page(request: Request):
        return templates.TemplateResponse("status.html", {
            "request": request,
            "bot_name": getattr(bot, "user", None) and bot.user.name or "Echo",
            "bot_avatar": _bot_avatar_url(),
        })

    @app.get("/api/status")
    async def api_status():
        import time, platform

        # ── Bot info ────────────────────────────────────────
        bot_user = getattr(bot, "user", None)
        bot_latency_ms = round(bot.latency * 1000, 1) if bot.latency and bot.latency != float("inf") else None

        # Uptime
        start_time = getattr(bot, "start_time", None)
        uptime_sec = int(time.time() - start_time) if start_time else None
        def fmt_uptime(s):
            if s is None: return "Unknown"
            d, rem = divmod(s, 86400)
            h, rem = divmod(rem, 3600)
            m, _ = divmod(rem, 60)
            parts = []
            if d: parts.append(f"{d}d")
            if h: parts.append(f"{h}h")
            parts.append(f"{m}m")
            return " ".join(parts)

        # ── Lavalink nodes ──────────────────────────────────
        lavalink = getattr(bot, "lavalink", None)
        nodes_data = []
        if lavalink:
            for node in lavalink.node_manager.nodes:
                node_stats = getattr(node, "stats", None)
                nodes_data.append({
                    "name": node.name,
                    "host": f"{node._transport._host}:{node._transport._port}" if hasattr(node, "_transport") else "Unknown",
                    "connected": node.available,
                    "ssl": getattr(node._transport, "_ssl", False) if hasattr(node, "_transport") else False,
                    "players": getattr(node_stats, "playing_players", 0) if node_stats else 0,
                    "cpu": round(getattr(node_stats, "cpu", {}).get("system_load", 0) * 100, 1) if node_stats and hasattr(node_stats, "cpu") and node_stats.cpu else None,
                    "memory_used": getattr(node_stats, "memory", {}).get("used", None) if node_stats and hasattr(node_stats, "memory") and node_stats.memory else None,
                })

        nodes_up = sum(1 for n in nodes_data if n["connected"])
        nodes_total = len(nodes_data)

        return {
            "bot": {
                "online": bot_user is not None,
                "name": bot_user.name if bot_user else "Echo",
                "id": str(bot_user.id) if bot_user else None,
                "avatar": _bot_avatar_url(),
                "guilds": len(bot.guilds),
                "users": sum(g.member_count or 0 for g in bot.guilds),
                "latency_ms": bot_latency_ms,
                "uptime": fmt_uptime(uptime_sec),
                "uptime_sec": uptime_sec,
                "python": platform.python_version(),
            },
            "lavalink": {
                "nodes": nodes_data,
                "up": nodes_up,
                "total": nodes_total,
                "status": "operational" if nodes_up == nodes_total and nodes_total > 0 else (
                    "degraded" if nodes_up > 0 else "down"
                ),
            },
            "dashboard": {
                "status": "operational",
                "port": DASHBOARD_PORT,
            },
            "timestamp": int(time.time()),
        }

    # ── JSON API ─────────────────────────────────────────────────

    @app.get("/api/me")
    async def api_me(request: Request):
        session = require_session(request)
        return {
            "id": session["id"],
            "username": session["username"],
            "avatar": oauth.avatar_url(session["id"], session.get("avatar")),
        }

    @app.get("/api/guilds")
    async def api_guilds(request: Request):
        session = require_session(request)
        user_id = int(session["id"])

        cache = app.state.guild_cache.get(session["id"])
        if not cache:
            raise HTTPException(status_code=401, detail="Session expired")
        user_guilds = cache["guilds"]

        result = []
        for ug in user_guilds:
            guild_id_int = int(ug["id"])
            g = bot.get_guild(guild_id_int)
            
            perms = int(ug.get("permissions", 0))
            is_admin = (perms & 0x8) == 0x8 or (perms & 0x20) == 0x20 or ug.get("owner", False)
            
            if g:
                level = await member_permission_level(g, user_id)
                if level is not None:
                    lavalink = getattr(bot, "lavalink", None)
                    player = lavalink.player_manager.get(g.id) if lavalink else None
                    is_playing = bool(player and player.is_connected and player.current)
                    
                    result.append({
                        "id": str(g.id),
                        "name": g.name,
                        "icon": g.icon.url if g.icon else None,
                        "member_count": g.member_count,
                        "permission_level": level,
                        "is_playing": is_playing,
                        "bot_present": True
                    })
            else:
                if is_admin:
                    icon_hash = ug.get("icon")
                    icon_url = f"https://cdn.discordapp.com/icons/{ug['id']}/{icon_hash}.png" if icon_hash else None
                    
                    bot_id = bot.user.id if bot.user else ""
                    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={bot_id}&permissions=8&scope=bot%20applications.commands&guild_id={ug['id']}&disable_guild_select=true"
                    
                    result.append({
                        "id": ug["id"],
                        "name": ug["name"],
                        "icon": icon_url,
                        "member_count": 0,
                        "permission_level": "admin" if ug.get("owner") else "manager",
                        "is_playing": False,
                        "bot_present": False,
                        "invite_url": invite_url
                    })
                    
        result.sort(key=lambda x: (not x["bot_present"], x["name"]))
        return {"guilds": result}

    @app.get("/api/guilds/{guild_id}/player")
    async def api_player_state(request: Request, guild_id: int):
        session = require_session(request)
        guild = bot.get_guild(guild_id)
        if not guild or await member_permission_level(guild, int(session["id"])) is None:
            raise HTTPException(status_code=403, detail="Forbidden")
        return player_to_dict(guild_id)

    @app.get("/api/guilds/{guild_id}/settings")
    async def api_get_settings(request: Request, guild_id: int):
        session = require_session(request)
        guild = bot.get_guild(guild_id)
        level = await member_permission_level(guild, int(session["id"])) if guild else None
        if level is None:
            raise HTTPException(status_code=403, detail="Forbidden")
        prefix = await bot.db.get_prefix(guild_id) or "Echo_config_default"
        twentyfourseven = await bot.db.get_247(guild_id)
        twentyfourseven_channel_id = await bot.db.get_247_channel(guild_id)
        
        voice_channels = []
        if guild:
            voice_channels = [
                {"id": str(vc.id), "name": vc.name}
                for vc in guild.voice_channels
            ]
            
        return {
            "prefix": prefix if prefix != "Echo_config_default" else ">",
            "twentyfourseven": twentyfourseven,
            "twentyfourseven_channel_id": str(twentyfourseven_channel_id) if twentyfourseven_channel_id else None,
            "voice_channels": voice_channels,
            "can_edit": level in ("owner", "manager"),
        }

    @app.post("/api/guilds/{guild_id}/settings")
    async def api_set_settings(request: Request, guild_id: int):
        session = require_session(request)
        guild = bot.get_guild(guild_id)
        level = await member_permission_level(guild, int(session["id"])) if guild else None
        if level not in ("owner", "manager"):
            raise HTTPException(status_code=403, detail="Requires Manage Server permission")

        body = await request.json()
        if "prefix" in body:
            new_prefix = str(body["prefix"])[:5]
            if new_prefix:
                await bot.db.set_prefix(guild_id, new_prefix)
        if "twentyfourseven" in body:
            val = bool(body["twentyfourseven"])
            await bot.db.set_247(guild_id, val)
            if val:
                # Fallback: if they turn it on and we already have a VC session active, record it
                guild = bot.get_guild(guild_id)
                if guild and guild.voice_client and guild.voice_client.channel:
                    await bot.db.set_247_channel(guild_id, guild.voice_client.channel.id)
        if "twentyfourseven_channel_id" in body:
            chan_id = body["twentyfourseven_channel_id"]
            if chan_id:
                try:
                    await bot.db.set_247_channel(guild_id, int(chan_id))
                except (ValueError, TypeError):
                    pass
            else:
                await bot.db.set_247_channel(guild_id, None)

        return {"ok": True}

    # ── Playlists API ───────────────────────────────────────────

    @app.get("/api/playlists")
    async def api_get_playlists(request: Request):
        session = require_session(request)
        user_id = int(session["id"])
        playlists = await bot.db.get_playlists(user_id)
        result = []
        for p in playlists:
            code = p[4]
            if not code:
                code = await bot.db.ensure_playlist_code(p[0])
            result.append({
                "id": p[0],
                "name": p[1],
                "created_at": p[2],
                "track_count": p[3],
                "code": code,
                "is_public": bool(p[5])
            })
        return result

    @app.post("/api/playlists")
    async def api_create_playlist(request: Request):
        session = require_session(request)
        user_id = int(session["id"])
        body = await request.json()
        name = body.get("name", "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Playlist name cannot be empty")
        existing = await bot.db.get_playlist_by_name(user_id, name)
        if existing:
            raise HTTPException(status_code=400, detail="A playlist with that name already exists")
        playlist_id, code = await bot.db.create_playlist(user_id, name)
        return {"id": playlist_id, "name": name, "code": code, "is_public": False}

    @app.patch("/api/playlists/{playlist_id}")
    async def api_rename_playlist(request: Request, playlist_id: int):
        session = require_session(request)
        user_id = int(session["id"])
        body = await request.json()
        new_name = body.get("name", "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Playlist name cannot be empty")
        existing = await bot.db.get_playlist_by_name(user_id, new_name)
        if existing and existing[0] != playlist_id:
            raise HTTPException(status_code=400, detail="A playlist with that name already exists")
        ok = await bot.db.rename_playlist(user_id, playlist_id, new_name)
        if not ok:
            raise HTTPException(status_code=404, detail="Playlist not found")
        return {"ok": True}

    @app.delete("/api/playlists/{playlist_id}")
    async def api_delete_playlist(request: Request, playlist_id: int):
        session = require_session(request)
        user_id = int(session["id"])
        ok = await bot.db.delete_playlist(user_id, playlist_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Playlist not found")
        return {"ok": True}

    @app.patch("/api/playlists/{playlist_id}/privacy")
    async def api_set_playlist_privacy(request: Request, playlist_id: int):
        session = require_session(request)
        user_id = int(session["id"])
        body = await request.json()
        is_public = bool(body.get("is_public", False))
        ok = await bot.db.set_playlist_privacy(user_id, playlist_id, is_public)
        if not ok:
            raise HTTPException(status_code=404, detail="Playlist not found")
        return {"ok": True, "is_public": is_public}

    @app.get("/api/playlists/code/{code}")
    async def api_get_playlist_by_code(request: Request, code: str):
        """Lookup any playlist by share code. Returns info if public (or owner)."""
        playlist = await bot.db.get_playlist_by_code(code.upper())
        if not playlist:
            raise HTTPException(status_code=404, detail="No playlist found with that code")
        # Check auth - allow if public or owner
        try:
            session = require_session(request)
            user_id = int(session["id"])
        except Exception:
            user_id = None
        is_owner = user_id == playlist[2]
        if not playlist[4] and not is_owner:  # not public and not owner
            raise HTTPException(status_code=403, detail="This playlist is private")
        tracks = await bot.db.get_playlist_tracks(playlist[0])
        return {
            "id": playlist[0],
            "name": playlist[1],
            "track_count": playlist[3],
            "is_public": bool(playlist[4]),
            "code": playlist[5],
            "is_owner": is_owner,
            "tracks": [
                {"id": t[0], "title": t[1], "author": t[2], "uri": t[3], "identifier": t[4]}
                for t in tracks
            ]
        }

    @app.get("/api/leaderboard")
    async def api_get_leaderboard(request: Request, timeframe: str = "all"):
        """Get the public playlist leaderboard."""
        require_session(request)
        raw_leaderboard = await bot.db.get_playlist_leaderboard(timeframe, limit=20)
        
        leaderboard = []
        for row in raw_leaderboard:
            playlist_id, name, owner_id, code, play_count, track_count = row
            
            owner_name = f"User {owner_id}"
            user = bot.get_user(owner_id)
            if user:
                owner_name = user.name
            else:
                try:
                    user = await bot.fetch_user(owner_id)
                    if user:
                        owner_name = user.name
                except Exception:
                    pass
            
            leaderboard.append({
                "id": playlist_id,
                "name": name,
                "owner_id": owner_id,
                "owner_name": owner_name,
                "code": code,
                "play_count": play_count,
                "track_count": track_count
            })
            
        return leaderboard

    @app.get("/api/search")
    async def api_search(request: Request, query: str):
        session = require_session(request)
        query = query.strip()
        if not query:
            return {"tracks": []}

        music_cog = bot.get_cog("Music")
        if not music_cog or not music_cog.lavalink:
            raise HTTPException(status_code=500, detail="Music system is not available")

        player = music_cog.lavalink.player_manager.create(0)
        search_query = query
        if not (search_query.startswith("http://") or search_query.startswith("https://")):
            search_query = f"ytsearch:{search_query}"

        try:
            results = await player.node.get_tracks(search_query)
            if not results or not results.tracks:
                return {"tracks": []}
            return {
                "tracks": [
                    {
                        "title": track.title,
                        "author": track.author,
                        "uri": track.uri,
                        "identifier": track.identifier,
                        "duration": track.duration
                    }
                    for track in results.tracks[:10]
                ]
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Search failed: {e}")

    @app.get("/api/playlists/{playlist_id}/tracks")
    async def api_get_playlist_tracks(request: Request, playlist_id: int):
        session = require_session(request)
        user_id = int(session["id"])
        playlist = await bot.db.get_playlist(user_id, playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        tracks = await bot.db.get_playlist_tracks(playlist_id)
        return [
            {
                "id": t[0],
                "title": t[1],
                "author": t[2],
                "uri": t[3],
                "identifier": t[4],
                "added_at": t[5]
            }
            for t in tracks
        ]

    @app.post("/api/playlists/{playlist_id}/tracks")
    async def api_add_playlist_track(request: Request, playlist_id: int):
        session = require_session(request)
        user_id = int(session["id"])
        playlist = await bot.db.get_playlist(user_id, playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        body = await request.json()
        query = body.get("query", "").strip()

        if query:
            music_cog = bot.get_cog("Music")
            if not music_cog or not music_cog.lavalink:
                raise HTTPException(status_code=500, detail="Music system is not available")
            
            player = music_cog.lavalink.player_manager.create(0)
            search_query = query
            if not (search_query.startswith("http://") or search_query.startswith("https://")):
                search_query = f"ytsearch:{search_query}"
            
            try:
                results = await player.node.get_tracks(search_query)
                if not results or not results.tracks:
                    raise HTTPException(status_code=400, detail=f"No results found for '{query}'")
                track = results.tracks[0]
                title = track.title
                author = track.author
                uri = track.uri
                identifier = track.identifier
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to resolve track: {e}")
        else:
            title = body.get("title", "").strip()
            author = body.get("author", "").strip()
            uri = body.get("uri", "").strip()
            identifier = body.get("identifier", "").strip() or None

        if not title or not uri:
            raise HTTPException(status_code=400, detail="Missing track title or uri")

        track_id = await bot.db.add_to_playlist(playlist_id, title, author, uri, identifier)
        return {"id": track_id, "title": title}

    @app.delete("/api/playlists/{playlist_id}/tracks/{track_id}")
    async def api_remove_playlist_track(request: Request, playlist_id: int, track_id: int):
        session = require_session(request)
        user_id = int(session["id"])
        playlist = await bot.db.get_playlist(user_id, playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        ok = await bot.db.remove_from_playlist(playlist_id, track_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Track not found")
        return {"ok": True}

    @app.post("/api/guilds/{guild_id}/play-playlist")
    async def api_play_playlist(request: Request, guild_id: int):
        session = require_session(request)
        user_id = int(session["id"])
        body = await request.json()
        playlist_id = body.get("playlist_id")
        if not playlist_id:
            raise HTTPException(status_code=400, detail="Missing playlist_id")

        guild = bot.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found")

        member = guild.get_member(user_id)
        if not member or not member.voice or not member.voice.channel:
            raise HTTPException(status_code=400, detail="You must be in a voice channel to play music")

        music_cog = bot.get_cog("Music")
        if not music_cog:
            raise HTTPException(status_code=500, detail="Music cog not loaded")

        playlist = await bot.db.get_playlist(user_id, playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        tracks = await bot.db.get_playlist_tracks(playlist_id)
        if not tracks:
            raise HTTPException(status_code=400, detail="Playlist is empty")

        from cogs.music import LavalinkVoiceClient

        player = music_cog.lavalink.player_manager.create(guild_id)

        if not guild.voice_client:
            perms = member.voice.channel.permissions_for(guild.me)
            if not perms.connect or not perms.speak:
                raise HTTPException(status_code=400, detail="Echo needs Connect and Speak permissions in your voice channel")
            player.store("channel", None)
            try:
                await member.voice.channel.connect(cls=LavalinkVoiceClient, self_deaf=True)
                await asyncio.sleep(0.5)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to join voice channel: {e}")
        elif guild.voice_client.channel != member.voice.channel:
            raise HTTPException(status_code=400, detail="Echo is already playing in a different voice channel")

        added_count = 0
        for t in tracks:
            track_title = t[1]
            track_uri = t[3]
            search_query = track_uri if track_uri else f"ytsearch:{track_title}"
            print(f"[PlayPlaylist] Searching track: '{track_title}' with query: '{search_query}'")
            try:
                results = await player.node.get_tracks(search_query)
                if results and results.tracks:
                    player.add(requester=user_id, track=results.tracks[0])
                    added_count += 1
                    print(f"[PlayPlaylist] Successfully added track: '{results.tracks[0].title}'")
                else:
                    print(f"[PlayPlaylist] No results found for query: '{search_query}'")
            except Exception as e:
                print(f"[PlayPlaylist] Exception while adding track '{track_title}': {e}")

        if added_count == 0:
            raise HTTPException(status_code=400, detail="Failed to load any tracks from the playlist")

        if not player.is_playing:
            try:
                await player.play()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Playback failed: {e}")

        await bot.db.record_playlist_play(playlist_id)
        await music_cog._notify_dashboard(guild_id)

        return {"ok": True, "message": f"Enqueued {added_count} tracks from playlist '{playlist[1]}'!"}

    @app.post("/api/guilds/{guild_id}/play-playlist-code")
    async def api_play_playlist_by_code(request: Request, guild_id: int):
        """Play a playlist by its share code (must be public, or owned by requester)."""
        session = require_session(request)
        user_id = int(session["id"])
        body = await request.json()
        code = body.get("code", "").strip().upper()
        if not code:
            raise HTTPException(status_code=400, detail="Missing playlist code")

        playlist = await bot.db.get_playlist_by_code(code)
        if not playlist:
            raise HTTPException(status_code=404, detail="No playlist found with that code")

        is_owner = user_id == playlist[2]
        if not playlist[4] and not is_owner:
            raise HTTPException(status_code=403, detail="This playlist is private")

        guild = bot.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found")

        member = guild.get_member(user_id)
        if not member or not member.voice or not member.voice.channel:
            raise HTTPException(status_code=400, detail="You must be in a voice channel to play music")

        music_cog = bot.get_cog("Music")
        if not music_cog:
            raise HTTPException(status_code=500, detail="Music cog not loaded")

        tracks = await bot.db.get_playlist_tracks(playlist[0])
        if not tracks:
            raise HTTPException(status_code=400, detail="Playlist is empty")

        from cogs.music import LavalinkVoiceClient
        player = music_cog.lavalink.player_manager.create(guild_id)

        if not guild.voice_client:
            perms = member.voice.channel.permissions_for(guild.me)
            if not perms.connect or not perms.speak:
                raise HTTPException(status_code=400, detail="Echo needs Connect and Speak permissions in your voice channel")
            player.store("channel", None)
            try:
                await member.voice.channel.connect(cls=LavalinkVoiceClient, self_deaf=True)
                await asyncio.sleep(0.5)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to join voice channel: {e}")
        elif guild.voice_client.channel != member.voice.channel:
            raise HTTPException(status_code=400, detail="Echo is already playing in a different voice channel")

        added_count = 0
        for t in tracks:
            track_title = t[1]
            track_uri = t[3]
            search_query = track_uri if track_uri else f"ytsearch:{track_title}"
            try:
                results = await player.node.get_tracks(search_query)
                if results and results.tracks:
                    player.add(requester=user_id, track=results.tracks[0])
                    added_count += 1
            except Exception as e:
                print(f"[PlayByCode] Exception for '{track_title}': {e}")

        if added_count == 0:
            raise HTTPException(status_code=400, detail="Failed to load any tracks from the playlist")

        if not player.is_playing:
            try:
                await player.play()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Playback failed: {e}")

        await bot.db.record_playlist_play(playlist[0])
        await music_cog._notify_dashboard(guild_id)
        return {"ok": True, "message": f"Enqueued {added_count} tracks from \"{playlist[1]}\"!", "playlist_name": playlist[1]}

    # ── Player control actions ──────────────────────────────────
    # These call the SAME lavalink player_manager the Discord
    # commands use — a dashboard click and a `>skip` command do
    # the exact same thing under the hood.

    async def _require_player_control(request: Request, guild_id: int):
        session = require_session(request)
        guild = bot.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found")
        level = await member_permission_level(guild, int(session["id"]))
        if level is None:
            raise HTTPException(status_code=403, detail="Forbidden")

        lavalink = getattr(bot, "lavalink", None)
        player = lavalink.player_manager.get(guild_id) if lavalink else None
        if not player or not player.is_connected:
            raise HTTPException(status_code=409, detail="Bot is not connected to a voice channel")

        # Managers/owners can always control. Regular members can
        # control only if they're actually sitting in the same voice
        # channel as the bot — mirrors normal in-Discord expectations.
        if level == "member":
            member = guild.get_member(int(session["id"]))
            bot_vc = guild.voice_client
            in_same_vc = (
                member and member.voice and bot_vc
                and member.voice.channel and member.voice.channel.id == bot_vc.channel.id
            )
            if not in_same_vc:
                raise HTTPException(
                    status_code=403,
                    detail="Join the voice channel Echo is in to control playback"
                )
        return player

    @app.post("/api/guilds/{guild_id}/pause")
    async def api_pause(request: Request, guild_id: int):
        player = await _require_player_control(request, guild_id)
        await player.set_pause(True)
        await broadcast_player_update(guild_id)
        return {"ok": True}

    @app.post("/api/guilds/{guild_id}/resume")
    async def api_resume(request: Request, guild_id: int):
        player = await _require_player_control(request, guild_id)
        await player.set_pause(False)
        await broadcast_player_update(guild_id)
        return {"ok": True}

    @app.post("/api/guilds/{guild_id}/skip")
    async def api_skip(request: Request, guild_id: int):
        player = await _require_player_control(request, guild_id)
        await player.skip()
        await broadcast_player_update(guild_id)
        return {"ok": True}

    @app.post("/api/guilds/{guild_id}/stop")
    async def api_stop(request: Request, guild_id: int):
        player = await _require_player_control(request, guild_id)
        player.queue.clear()
        await player.stop()
        await broadcast_player_update(guild_id)
        return {"ok": True}

    @app.post("/api/guilds/{guild_id}/volume")
    async def api_volume(request: Request, guild_id: int):
        player = await _require_player_control(request, guild_id)
        body = await request.json()
        vol = max(0, min(150, int(body.get("volume", 100))))
        await player.set_volume(vol)
        await broadcast_player_update(guild_id)
        return {"ok": True, "volume": vol}

    @app.post("/api/guilds/{guild_id}/loop")
    async def api_loop(request: Request, guild_id: int):
        player = await _require_player_control(request, guild_id)
        body = await request.json()
        player.loop = bool(body.get("loop", False))
        await broadcast_player_update(guild_id)
        return {"ok": True, "loop": player.loop}

    @app.post("/api/guilds/{guild_id}/shuffle")
    async def api_shuffle(request: Request, guild_id: int):
        player = await _require_player_control(request, guild_id)
        import random
        if player.queue:
            random.shuffle(player.queue)
        await broadcast_player_update(guild_id)
        return {"ok": True}

    @app.post("/api/guilds/{guild_id}/autoplay")
    async def api_autoplay(request: Request, guild_id: int):
        await _require_player_control(request, guild_id)
        music_cog = bot.get_cog("Music")
        if not music_cog:
            raise HTTPException(status_code=500, detail="Music system unavailable")
        body = await request.json()
        music_cog.autoplay_states[guild_id] = bool(body.get("autoplay", False))
        await broadcast_player_update(guild_id)
        return {"ok": True, "autoplay": music_cog.autoplay_states[guild_id]}

    @app.post("/api/guilds/{guild_id}/previous")
    async def api_previous(request: Request, guild_id: int):
        player = await _require_player_control(request, guild_id)
        music_cog = bot.get_cog("Music")
        if not music_cog:
            raise HTTPException(status_code=500, detail="Music system unavailable")
        ok = await music_cog.play_previous(guild_id)
        if not ok:
            raise HTTPException(status_code=409, detail="No previous track")
        await broadcast_player_update(guild_id)
        return {"ok": True}

    @app.post("/api/guilds/{guild_id}/replay")
    async def api_replay(request: Request, guild_id: int):
        player = await _require_player_control(request, guild_id)
        if not player.current:
            raise HTTPException(status_code=409, detail="Nothing is playing")
        await player.seek(0)
        await broadcast_player_update(guild_id)
        return {"ok": True}

    @app.post("/api/guilds/{guild_id}/queue/{index}/remove")
    async def api_queue_remove(request: Request, guild_id: int, index: int):
        player = await _require_player_control(request, guild_id)
        if 0 <= index < len(player.queue):
            player.queue.pop(index)
        await broadcast_player_update(guild_id)
        return {"ok": True}

    @app.post("/api/guilds/{guild_id}/play")
    async def api_play(request: Request, guild_id: int):
        """Queue a track from the dashboard search box. User must already
        be in a voice channel, same rule as the >play command."""
        session = require_session(request)
        guild = bot.get_guild(guild_id)
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found")
        if await member_permission_level(guild, int(session["id"])) is None:
            raise HTTPException(status_code=403, detail="Forbidden")

        member = guild.get_member(int(session["id"]))
        if not member or not member.voice or not member.voice.channel:
            raise HTTPException(status_code=400, detail="Join a voice channel in Discord first")

        body = await request.json()
        query = (body.get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="No search query given")

        music_cog = bot.get_cog("Music")
        if not music_cog:
            raise HTTPException(status_code=500, detail="Music system unavailable")

        ok, message = await music_cog.play_from_dashboard(guild, member, query)
        if not ok:
            raise HTTPException(status_code=400, detail=message)

        await broadcast_player_update(guild_id)
        return {"ok": True, "message": message}

    # ── WebSocket — live player sync ─────────────────────────────

    @app.websocket("/ws/{guild_id}")
    async def ws_player(websocket: WebSocket, guild_id: int):
        token = websocket.cookies.get("Echo_session")
        session = oauth.read_session_token(token) if token else None
        if not session:
            await websocket.close(code=4001)
            return

        guild = bot.get_guild(guild_id)
        if not guild or await member_permission_level(guild, int(session["id"])) is None:
            await websocket.close(code=4003)
            return

        await websocket.accept()
        app.state.ws_clients.setdefault(guild_id, set()).add(websocket)

        try:
            # Send initial state immediately on connect
            await websocket.send_json({"type": "player_update", "data": player_to_dict(guild_id)})
            while True:
                # We don't expect incoming messages other than pings —
                # all control goes through the REST endpoints above.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            app.state.ws_clients.get(guild_id, set()).discard(websocket)

    return app


async def run_dashboard(bot):
    """Entry point called from main.py — runs the dashboard server
    as a background task on the bot's own event loop.

    Deliberately does NOT call server.serve() — that method wraps
    everything in uvicorn's capture_signals(), which installs its own
    SIGINT/SIGTERM handlers. Since this task shares a process (and event
    loop) with the Discord bot, those handlers fight with asyncio's/the
    bot's own shutdown handling: on a host-issued stop, both try to react
    to the same signal, and this task's resulting KeyboardInterrupt had
    nowhere to go because nothing was awaiting it — hence the
    "Task exception was never retrieved" warning during shutdown.

    Calling startup()/main_loop()/shutdown() directly is uvicorn's own
    documented pattern for embedding the server inside another
    application's event loop instead of owning the process' signals.
    """
    import uvicorn

    app = create_dashboard(bot)
    config = uvicorn.Config(app, host="0.0.0.0", port=DASHBOARD_PORT, log_level="warning")
    server = uvicorn.Server(config)
    bot.dashboard_server = server  # so bot shutdown can trigger a clean stop
    print(f"  🌐 Dashboard starting on http://0.0.0.0:{DASHBOARD_PORT}")
    try:
        if not config.loaded:
            config.load()
        server.lifespan = config.lifespan_class(config)
        await server.startup()
        await server.main_loop()
    except asyncio.CancelledError:
        pass  # normal path when the bot cancels this task on shutdown
    finally:
        try:
            await server.shutdown()
        except Exception:
            pass
