"""
Music cog for Rose - lavalink.py based player with YouTube, Spotify
and Apple Music support, 24/7 mode, autoplay and live VC status.
"""

import discord
from discord.ext import commands
from discord import ui
import lavalink
import re
import random
import asyncio
from config import Config
import emojis
from utils.helpers import format_time, truncate


# node list lives in config.py (Config.LAVALINK_NODES)

URL_REGEX = re.compile(r"https?://(?:www\.)?.+")

MAX_QUEUE_DISPLAY = 10


# helpers

def make_text_container(text: str) -> ui.LayoutView:
    view = ui.LayoutView()
    container = ui.Container(accent_colour=None)
    container.add_item(ui.TextDisplay(text))
    view.add_item(container)
    return view


def format_duration(ms: int) -> str:
    if not ms or ms <= 0:
        return "00:00"
    s = int(ms / 1000)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def get_source_emoji_from_uri(uri: str) -> str:
    if not uri:
        return emojis.MUSIC
    u = uri.lower()
    if "spotify" in u:
        return emojis.SPOTIFY
    elif "apple" in u:
        return emojis.APPLE_MUSIC
    elif "soundcloud" in u:
        return emojis.SOUNDCLOUD
    elif "youtube" in u or "youtu.be" in u:
        return emojis.YOUTUBE
    return emojis.MUSIC


def make_thumbnail(url: str):
    """Create a Thumbnail component with proper UnfurledMediaItem."""
    return ui.Thumbnail(media=discord.UnfurledMediaItem(url=url))


# lavalink voice client

class LavalinkVoiceClient(discord.VoiceProtocol):
    """VoiceProtocol implementation for lavalink.py v5+"""

    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        self.client = client
        self.channel = channel
        self._guild = channel.guild
        self._destroyed = False

        if not hasattr(client, "lavalink") or client.lavalink is None:
            raise RuntimeError("Lavalink client not initialized on bot!")

        self.lavalink: lavalink.Client = client.lavalink

    async def on_voice_server_update(self, data: dict):
        lavalink_data = {
            "t": "VOICE_SERVER_UPDATE",
            "d": {
                "guild_id": str(self._guild.id),
                "token": data["token"],
                "endpoint": data["endpoint"],
            }
        }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def on_voice_state_update(self, data: dict):
        channel_id = data.get("channel_id")

        if not channel_id:
            self.cleanup()
            player = self.lavalink.player_manager.get(self._guild.id)
            if player:
                player.channel_id = None
            return

        channel = self._guild.get_channel(int(channel_id))
        if channel:
            self.channel = channel

        lavalink_data = {
            "t": "VOICE_STATE_UPDATE",
            "d": {
                "guild_id": str(self._guild.id),
                "user_id": str(self.client.user.id),
                "channel_id": channel_id,
                "session_id": data.get("session_id", ""),
            }
        }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def connect(self, *, timeout: float, reconnect: bool,
                      self_deaf: bool = True, self_mute: bool = False) -> None:
        self.lavalink.player_manager.create(guild_id=self._guild.id)
        await self._guild.change_voice_state(
            channel=self.channel,
            self_mute=self_mute,
            self_deaf=self_deaf,
        )

    async def disconnect(self, *, force: bool = False) -> None:
        player = self.lavalink.player_manager.get(self._guild.id)

        if not force and player and not player.is_connected:
            return

        await self._guild.change_voice_state(channel=None)
        self.cleanup()

        if not self._destroyed:
            self._destroyed = True
            try:
                await self.lavalink.player_manager.destroy(self._guild.id)
            except Exception:
                pass

    async def move_to(self, channel: discord.abc.Connectable):
        await self._guild.change_voice_state(channel=channel)
        self.channel = channel

    def is_connected(self) -> bool:
        """Check if voice client is connected."""
        return self.channel is not None and not self._destroyed


# now playing layout

class NowPlayingLayout(ui.LayoutView):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.message: discord.Message = None

    def build(self, player):
        self.clear_items()
        track = player.current

        if not track:
            container = ui.Container(accent_colour=None)
            container.add_item(ui.TextDisplay(f"{emojis.ERROR} Nothing is playing."))
            self.add_item(container)
            return self

        src = get_source_emoji_from_uri(track.uri)
        status = "Paused" if player.paused else "Playing"
        req_user = self.cog.bot.get_user(track.requester)
        req_str = str(req_user) if req_user else "Unknown"

        container = ui.Container(accent_colour=None)
        container.add_item(ui.TextDisplay(f"### {emojis.PLAYING} Now Playing"))
        container.add_item(ui.Separator())

        info_text = (
            f"### {src} [{track.title}]({track.uri})\n"
            f"{emojis.DOT} **Artist:** {track.author}\n"
            f"{emojis.DOT} **Duration:** `{format_duration(track.duration)}`\n"
            f"{emojis.DOT} **Status:** `{status}`\n"
            f"{emojis.DOT} **Volume:** `{player.volume}%`\n"
            f"{emojis.DOT} **Loop:** `{'On' if player.loop else 'Off'}`"
        )

        thumb = self.cog._get_thumbnail(track)
        if thumb:
            try:
                section = ui.Section(accessory=make_thumbnail(thumb))
                section.add_item(ui.TextDisplay(info_text))
                container.add_item(section)
            except Exception as e:
                print(f"[NP Thumbnail Error] {e}")
                container.add_item(ui.TextDisplay(info_text))
        else:
            container.add_item(ui.TextDisplay(info_text))

        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(f"-# Requested by {req_str}"))
        container.add_item(ui.Separator())

        # Row 1
        row1 = ui.ActionRow()
        pause_label = "Resume" if player.paused else "Pause"
        pause_emoji = emojis.BTN_RESUME if player.paused else emojis.BTN_PAUSE
        row1.add_item(NPButton("pause", pause_label, pause_emoji,
                               discord.ButtonStyle.primary, self))
        row1.add_item(NPButton("skip", "Skip", emojis.BTN_SKIP,
                               discord.ButtonStyle.secondary, self))
        row1.add_item(NPButton("stop", "Stop", emojis.BTN_STOP,
                               discord.ButtonStyle.danger, self))
        container.add_item(row1)

        # Row 2
        row2 = ui.ActionRow()
        loop_style = (discord.ButtonStyle.success if player.loop
                      else discord.ButtonStyle.secondary)
        row2.add_item(NPButton("loop", "Loop", emojis.BTN_LOOP, loop_style, self))

        ap_on = self.cog.autoplay_states.get(self.guild_id, False)
        ap_style = (discord.ButtonStyle.success if ap_on
                    else discord.ButtonStyle.secondary)
        row2.add_item(NPButton("autoplay", "Autoplay", emojis.BTN_AUTOPLAY, ap_style, self))
        container.add_item(row2)

        self.add_item(container)
        return self


class NPButton(ui.Button):
    def __init__(self, action: str, label: str, emoji_str: str,
                 style: discord.ButtonStyle, layout: NowPlayingLayout):
        super().__init__(label=label, emoji=emoji_str, style=style)
        self.action = action
        self.layout = layout

    async def callback(self, interaction: discord.Interaction):
        cog = self.layout.cog
        player = cog.lavalink.player_manager.get(interaction.guild.id)

        if not player:
            return await interaction.response.send_message(
                f"{emojis.ERROR} Player not found.", ephemeral=True
            )

        if not interaction.user.voice or not interaction.guild.voice_client:
            return await interaction.response.send_message(
                "You must be in the same voice channel.", ephemeral=True
            )

        if interaction.user.voice.channel != interaction.guild.voice_client.channel:
            return await interaction.response.send_message(
                "You must be in the same voice channel.", ephemeral=True
            )

        if self.action == "pause":
            await player.set_pause(not player.paused)
            self.layout.build(player)
            await interaction.response.edit_message(view=self.layout)

        elif self.action == "skip":
            await player.skip()
            await interaction.response.send_message(
                f"{emojis.BTN_SKIP} Skipped", ephemeral=True
            )

        elif self.action == "stop":
            player.queue.clear()
            await player.stop()
            cog.now_playing_messages.pop(interaction.guild.id, None)
            
            is_247 = await cog.bot.db.get_247(interaction.guild.id)
            if not is_247:
                cog._start_idle_timer(interaction.guild.id)
            else:
                await cog._update_vc_status(interaction.guild.id, f"{emojis.INFO} Waiting for listeners")

            await interaction.response.send_message(
                f"{emojis.BTN_STOP} Playback stopped and queue cleared.", ephemeral=True
            )

        elif self.action == "loop":
            player.set_loop(0 if player.loop else 1)
            self.layout.build(player)
            await interaction.response.edit_message(view=self.layout)
            await interaction.followup.send(
                f"Loop: **{'On' if player.loop else 'Off'}**", ephemeral=True
            )

        elif self.action == "autoplay":
            current = cog.autoplay_states.get(interaction.guild.id, False)
            cog.autoplay_states[interaction.guild.id] = not current
            self.layout.build(player)
            await interaction.response.edit_message(view=self.layout)
            await interaction.followup.send(
                f"Autoplay: **{'Enabled' if not current else 'Disabled'}**",
                ephemeral=True
            )

        # Every in-Discord control mutates player/autoplay state, so push
        # the change to any connected dashboard clients too — otherwise
        # the website goes stale the moment someone uses these buttons.
        await cog._notify_dashboard(interaction.guild.id)



class Music(commands.Cog, name="Music"):
    """Music commands — play from YouTube, Spotify, Apple Music."""

    def __init__(self, bot):
        self.bot = bot
        self.lavalink: lavalink.Client = None
        self.now_playing_messages: dict[int, discord.Message] = {}
        self.autoplay_states: dict[int, bool] = {}
        self.recent_tracks: dict[int, list] = {}
        self.history: dict[int, list] = {}  # guild_id -> [track, ...] most-recent last, for Previous
        self._last_announced: dict[int, str] = {}
        self.idle_tasks: dict[int, asyncio.Task] = {}
        self._node_ready = asyncio.Event()
        bot.loop.create_task(self._init_lavalink())

    def cog_unload(self):
        if self.lavalink:
            try:
                self.lavalink._event_hooks.clear()
            except Exception:
                pass
        for task in self.idle_tasks.values():
            if not task.done():
                task.cancel()

    # ─── Lavalink Init ───

    async def _init_lavalink(self):
        await self.bot.wait_until_ready()

        if not hasattr(self.bot, "lavalink") or self.bot.lavalink is None:
            self.bot.lavalink = lavalink.Client(self.bot.user.id)
            print(f"[Music] Lavalink client created for bot ID {self.bot.user.id}")

        self.lavalink = self.bot.lavalink

        # Clear old hooks
        try:
            for k in list(self.lavalink._event_hooks.keys()):
                self.lavalink._event_hooks[k] = [
                    h for h in self.lavalink._event_hooks[k]
                    if not isinstance(getattr(h, "__self__", None), Music)
                ]
        except Exception:
            pass

        self.lavalink.add_event_hooks(self)

        # Add nodes
        for node in Config.LAVALINK_NODES:
            try:
                existing = [
                    n for n in self.lavalink.node_manager.nodes
                    if n.name == node["name"]
                ]
                if existing:
                    continue

                self.lavalink.add_node(
                    host=node["host"],
                    port=node["port"],
                    password=node["password"],
                    region=node["region"],
                    name=node["name"],
                    ssl=node.get("ssl", False),
                )
                print(f"[Music] Added node '{node['name']}' ({node['host']}:{node['port']})")
            except Exception as e:
                print(f"[Music] Failed to add node '{node['name']}': {e}")

        # Wait for connection
        print("[Music] Waiting for Lavalink node...")
        for attempt in range(60):
            if self.lavalink.node_manager.available_nodes:
                self._node_ready.set()
                print(f"[Music] Node ready after {attempt + 1}s!")
                self.bot.loop.create_task(self._auto_reconnect_247())
                return
            await asyncio.sleep(1)

        print("[Music] WARNING: No Lavalink nodes connected after 60s!")

    async def _auto_reconnect_247(self):
        await asyncio.sleep(2)  # brief delay to let bot settle
        try:
            guilds_247 = await self.bot.db.get_all_247_guilds()
        except Exception as e:
            print(f"[AutoReconnect] Failed to fetch 24/7 guilds: {e}")
            return

        if not guilds_247:
            return

        print(f"[AutoReconnect] Found {len(guilds_247)} guild(s) with active 24/7 settings.")
        for guild_id, channel_id in guilds_247:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print(f"[AutoReconnect] Guild {guild_id} not found/cached.")
                continue

            channel = guild.get_channel(channel_id)
            if not channel:
                print(f"[AutoReconnect] Channel {channel_id} not found in guild '{guild.name}'.")
                continue

            if guild.voice_client:
                print(f"[AutoReconnect] Already connected to voice in guild '{guild.name}'.")
                continue

            try:
                player = self.lavalink.player_manager.create(guild_id)
                player.store("channel", None)
                print(f"[AutoReconnect] Reconnecting to voice channel '{channel.name}' in '{guild.name}'...")
                await channel.connect(cls=LavalinkVoiceClient, self_deaf=True)
                await self._update_vc_status(guild_id, f"{emojis.INFO} Waiting for listeners")
                print(f"[AutoReconnect] Connected successfully in '{guild.name}'.")
            except Exception as e:
                print(f"[AutoReconnect] Failed to connect in '{guild.name}': {e}")

    # ─── Voice cleanup ───

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                     before: discord.VoiceState,
                                     after: discord.VoiceState):
        if member.id != self.bot.user.id:
            return
        
        guild_id = member.guild.id
        if before.channel and not after.channel:
            await self._clear_vc_status(guild_id)
            if self.lavalink:
                player = self.lavalink.player_manager.get(guild_id)
                if player:
                    player.channel_id = None
            await self.bot.db.set_247_channel(guild_id, None)
        elif after.channel:
            is_247 = await self.bot.db.get_247(guild_id)
            if is_247:
                await self.bot.db.set_247_channel(guild_id, after.channel.id)

    # ─── Lavalink Events ───

    @lavalink.listener(lavalink.events.NodeConnectedEvent)
    async def on_node_connected(self, event):
        self._node_ready.set()
        print(f"[Music] Node '{event.node.name}' connected!")

    @lavalink.listener(lavalink.events.NodeDisconnectedEvent)
    async def on_node_disconnected(self, event):
        if not self.lavalink.node_manager.available_nodes:
            self._node_ready.clear()
        print(f"[Music] Node '{event.node.name}' disconnected!")

    async def _notify_dashboard(self, guild_id: int):
        """Push a live update to any connected dashboard clients for this
        guild. No-op if the dashboard isn't running."""
        broadcaster = getattr(self.bot, "dashboard_broadcast", None)
        if broadcaster:
            try:
                await broadcaster(guild_id)
            except Exception as e:
                print(f"[Dashboard] broadcast failed: {e}")

    @lavalink.listener(lavalink.events.TrackStartEvent)
    async def on_track_start(self, event: lavalink.events.TrackStartEvent):
        player = event.player
        guild_id = int(player.guild_id)
        track = event.track

        existing = self.idle_tasks.pop(guild_id, None)
        if existing and not existing.done():
            existing.cancel()

        # Real-time VC status update
        status_text = f"{emojis.MYMUSIC} Playing: {track.title}"
        await self._update_vc_status(guild_id, status_text)

        hist = self.history.setdefault(guild_id, [])
        if not hist or hist[-1].identifier != track.identifier:
            hist.append(track)
            if len(hist) > 15:
                hist.pop(0)

        await self._notify_dashboard(guild_id)

        if self._last_announced.get(guild_id) == track.identifier:
            await self._update_now_playing(guild_id)
            return

        self._last_announced[guild_id] = track.identifier

        recent = self.recent_tracks.setdefault(guild_id, [])
        recent.append(track.identifier)
        if len(recent) > 5:
            recent.pop(0)

        await self._send_now_playing(guild_id, player)

    @lavalink.listener(lavalink.events.TrackEndEvent)
    async def on_track_end(self, event: lavalink.events.TrackEndEvent):
        self._last_announced.pop(int(event.player.guild_id), None)
        await self._notify_dashboard(int(event.player.guild_id))

    @lavalink.listener(lavalink.events.TrackExceptionEvent)
    async def on_track_exception(self, event: lavalink.events.TrackExceptionEvent):
        guild_id = int(event.player.guild_id)
        channel_id = event.player.fetch("channel")
        guild = self.bot.get_guild(guild_id)
        print(f"[Music] Track exception in {guild_id}: {event.exception}")
        if guild and channel_id:
            ch = guild.get_channel(channel_id)
            if ch:
                view = make_text_container(f"{emojis.ERROR} Track error: `{event.exception}`")
                try:
                    await ch.send(view=view)
                except Exception:
                    pass

    @lavalink.listener(lavalink.events.TrackStuckEvent)
    async def on_track_stuck(self, event: lavalink.events.TrackStuckEvent):
        print(f"[Music] Track stuck, skipping...")
        await event.player.skip()

    @lavalink.listener(lavalink.events.QueueEndEvent)
    async def on_queue_end(self, event: lavalink.events.QueueEndEvent):
        player = event.player
        guild_id = int(player.guild_id)
        self._last_announced.pop(guild_id, None)
        await self._notify_dashboard(guild_id)

        # Autoplay
        if self.autoplay_states.get(guild_id, False):
            if await self._try_autoplay(guild_id, player):
                return

        # 24/7 check
        is_247 = await self.bot.db.get_247(guild_id)
        if is_247:
            # Set "Waiting for listeners" status
            await self._update_vc_status(
                guild_id, f"{emojis.INFO} Waiting for listeners"
            )
            msg = self.now_playing_messages.pop(guild_id, None)
            if msg:
                try:
                    view = make_text_container(
                        f"{emojis.INFO} Queue ended — staying in VC (24/7 mode)."
                    )
                    await msg.edit(view=view)
                except discord.HTTPException:
                    pass
            return

        # Start idle timer
        self._start_idle_timer(guild_id)

        msg = self.now_playing_messages.pop(guild_id, None)
        if msg:
            try:
                view = make_text_container(
                    f"{emojis.INFO} Queue ended — idling for 5 minutes."
                )
                await msg.edit(view=view)
            except discord.HTTPException:
                pass

    def _start_idle_timer(self, guild_id: int):
        existing = self.idle_tasks.pop(guild_id, None)
        if existing and not existing.done():
            existing.cancel()
        task = self.bot.loop.create_task(self._idle_disconnect_delay(guild_id))
        self.idle_tasks[guild_id] = task

    async def _idle_disconnect_delay(self, guild_id: int):
        # Update voice status
        await self._update_vc_status(guild_id, f"{emojis.INFO} Idle — leaving soon")

        player = self.lavalink.player_manager.get(guild_id)
        channel_id = player.fetch("channel") if player else None
        guild = self.bot.get_guild(guild_id)
        ch = None

        if guild and channel_id:
            ch = guild.get_channel(channel_id)
            if ch:
                try:
                    view = make_text_container(f"{emojis.INFO} Queue ended. I will disconnect in 5 minutes if no songs are added.")
                    await ch.send(view=view)
                except Exception:
                    pass

        try:
            await asyncio.sleep(300.0) # 5 minutes
            player = self.lavalink.player_manager.get(guild_id)
            if player and not player.is_playing:
                await self._clear_vc_status(guild_id)
                if guild and guild.voice_client:
                    try:
                        await guild.voice_client.disconnect(force=True)
                    except Exception:
                        pass
                await self._notify_dashboard(guild_id)
                if ch:
                    try:
                        view = make_text_container(f"{emojis.INFO} Left the voice channel due to inactivity.")
                        await ch.send(view=view)
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass
        finally:
            self.idle_tasks.pop(guild_id, None)

    # ─── Autoplay ───

    async def _try_autoplay(self, guild_id: int, player) -> bool:
        recent = self.recent_tracks.get(guild_id, [])
        if not recent:
            return False
        seed = recent[-1]
        try:
            mix = f"https://www.youtube.com/watch?v={seed}&list=RD{seed}"
            res = await player.node.get_tracks(mix)
            if not res or not res.tracks:
                return False
            added = 0
            for t in res.tracks:
                if t.identifier in recent:
                    continue
                player.add(requester=self.bot.user.id, track=t)
                added += 1
                if added >= 5:
                    break
            if added > 0 and (not player.is_playing or not player.current):
                await player.play()
            return added > 0
        except Exception as e:
            print(f"[Autoplay] Error: {e}")
            return False

    # ─── Internal helpers ───

    def _get_thumbnail(self, track) -> str:
        """Get best available thumbnail URL for a track."""
        if not track:
            return None

        # Try artwork_url first (Spotify, Apple Music, SoundCloud have this)
        artwork = getattr(track, 'artwork_url', None)
        if artwork:
            return artwork

        # For YouTube, use hqdefault (always available, unlike maxresdefault)
        try:
            source = getattr(track, 'source_name', '').lower()
            uri = (track.uri or '').lower()

            if 'youtube' in source or 'youtube' in uri or 'youtu.be' in uri:
                return f"https://img.youtube.com/vi/{track.identifier}/hqdefault.jpg"
        except Exception:
            pass

        return None

    async def _update_vc_status(self, guild_id: int, text: str):
        """Update voice channel status text."""
        guild = self.bot.get_guild(guild_id)
        if not guild or not guild.voice_client:
            return
        channel = guild.voice_client.channel
        if not channel:
            return
        try:
            await self.bot.http.request(
                discord.http.Route(
                    "PUT", "/channels/{channel_id}/voice-status",
                    channel_id=channel.id,
                ),
                json={"status": text[:500]},
            )
        except Exception as e:
            print(f"[VC Status] {e}")

    async def _clear_vc_status(self, guild_id: int):
        """Clear voice channel status."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        for vc in guild.voice_channels:
            try:
                await self.bot.http.request(
                    discord.http.Route(
                        "PUT", "/channels/{channel_id}/voice-status",
                        channel_id=vc.id,
                    ),
                    json={"status": ""},
                )
            except Exception:
                pass

    async def _send_now_playing(self, guild_id: int, player):
        channel_id = player.fetch("channel")
        guild = self.bot.get_guild(guild_id)
        if not guild or not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return

        layout = NowPlayingLayout(self, guild_id)
        layout.build(player)

        old = self.now_playing_messages.get(guild_id)
        if old:
            try:
                await old.delete()
            except discord.HTTPException:
                pass

        try:
            msg = await channel.send(view=layout)
            layout.message = msg
            self.now_playing_messages[guild_id] = msg
        except discord.HTTPException as e:
            print(f"[Now Playing] Send failed: {e}")

    async def _update_now_playing(self, guild_id: int):
        player = self.lavalink.player_manager.get(guild_id)
        msg = self.now_playing_messages.get(guild_id)
        if not player or not msg:
            return
        layout = NowPlayingLayout(self, guild_id)
        layout.build(player)
        try:
            await msg.edit(view=layout)
        except discord.HTTPException:
            pass

    async def _ensure_voice(self, ctx) -> bool:
        # Wait for lavalink node
        if not self._node_ready.is_set():
            view = make_text_container(f"{emojis.LOADING} Connecting to music server...")
            wait_msg = await ctx.send(view=view)
            try:
                await asyncio.wait_for(self._node_ready.wait(), timeout=20)
            except asyncio.TimeoutError:
                view = make_text_container(
                    f"{emojis.ERROR} Music server unavailable. Try again later."
                )
                await wait_msg.edit(view=view)
                return False
            try:
                await wait_msg.delete()
            except Exception:
                pass

        # Check user VC
        if not ctx.author.voice or not ctx.author.voice.channel:
            view = make_text_container(f"{emojis.ERROR} You must be in a voice channel.")
            await ctx.reply(view=view)
            return False

        vc = ctx.author.voice.channel
        player = self.lavalink.player_manager.create(ctx.guild.id)

        # Bot not connected
        if not ctx.guild.voice_client:
            perms = vc.permissions_for(ctx.guild.me)
            if not perms.connect or not perms.speak:
                view = make_text_container(
                    f"{emojis.ERROR} I need **Connect** and **Speak** permissions."
                )
                await ctx.reply(view=view)
                return False

            player.store("channel", ctx.channel.id)

            try:
                await vc.connect(cls=LavalinkVoiceClient, self_deaf=True)
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"[Connect] Error: {e}")
                view = make_text_container(f"{emojis.ERROR} Failed to connect: `{e}`")
                await ctx.reply(view=view)
                return False
        else:
            if ctx.guild.voice_client.channel != vc:
                view = make_text_container(f"{emojis.ERROR} You must be in my voice channel.")
                await ctx.reply(view=view)
                return False

        return True

    # dashboard bridge

    async def play_from_dashboard(self, guild: discord.Guild, member: discord.Member, query: str):
        """
        Same connect + search + queue pipeline as the `>play` command,
        called from dashboard/app.py's /api/guilds/{id}/play route.
        Returns (ok: bool, message: str) instead of editing a Discord
        message, since there's no ctx here.
        """
        if not self._node_ready.is_set():
            try:
                await asyncio.wait_for(self._node_ready.wait(), timeout=15)
            except asyncio.TimeoutError:
                return False, "Music server is unavailable right now."

        vc = member.voice.channel
        player = self.lavalink.player_manager.create(guild.id)

        if not guild.voice_client:
            perms = vc.permissions_for(guild.me)
            if not perms.connect or not perms.speak:
                return False, "Rose needs Connect and Speak permissions in that channel."
            player.store("channel", None)
            try:
                await vc.connect(cls=LavalinkVoiceClient, self_deaf=True)
                await asyncio.sleep(0.5)
            except Exception as e:
                return False, f"Failed to join voice channel: {e}"
        elif guild.voice_client.channel != vc:
            return False, "Rose is already playing in a different voice channel."

        search = query if URL_REGEX.match(query) else f"ytsearch:{query}"

        try:
            results = await player.node.get_tracks(search)
        except Exception as e:
            return False, f"Search failed: {e}"

        if not results or not results.tracks:
            return False, f"No results found for '{query}'."

        if results.load_type == lavalink.LoadType.PLAYLIST:
            for t in results.tracks:
                player.add(requester=member.id, track=t)
            message = f"Queued playlist '{results.playlist_info.name}' ({len(results.tracks)} tracks)."
        else:
            track = results.tracks[0]
            player.add(requester=member.id, track=track)
            message = f"Queued '{track.title}'."

        if not player.is_playing:
            try:
                await player.play()
            except Exception as e:
                return False, f"Playback failed: {e}"

        return True, message

    # commands

    @commands.hybrid_command(name="play", aliases=["p"])
    @commands.guild_only()
    async def play(self, ctx, *, query: str = None):
        """Play a song or playlist."""
        if not query:
            view = make_text_container(
                f"{emojis.ERROR} Provide a song name or URL.\n"
                f"Usage: `{ctx.prefix}play <song / url>`"
            )
            return await ctx.reply(view=view)

        if not await self._ensure_voice(ctx):
            return

        player = self.lavalink.player_manager.get(ctx.guild.id)
        player.store("channel", ctx.channel.id)

        # Resolve query
        if not URL_REGEX.match(query):
            search = f"ytsearch:{query}"
        else:
            search = query

        loading_view = make_text_container(f"{emojis.LOADING} Searching for **{query}**...")
        loading_msg = await ctx.reply(view=loading_view)

        try:
            results = await player.node.get_tracks(search)
        except Exception as e:
            print(f"[Search] {e}")
            view = make_text_container(f"{emojis.ERROR} Search failed: `{e}`")
            return await loading_msg.edit(view=view)

        if not results or not results.tracks:
            view = make_text_container(f"{emojis.ERROR} No results found for **{query}**.")
            return await loading_msg.edit(view=view)

        # Playlist
        if results.load_type == lavalink.LoadType.PLAYLIST:
            for t in results.tracks:
                player.add(requester=ctx.author.id, track=t)

            view = make_text_container(
                f"### {emojis.SUCCESS} Playlist Enqueued\n"
                f"{emojis.DOT} **Name:** {results.playlist_info.name}\n"
                f"{emojis.DOT} **Tracks:** `{len(results.tracks)}`\n"
                f"{emojis.DOT} **Requester:** {ctx.author.mention}"
            )
            await loading_msg.edit(view=view)

        # Single track
        else:
            track = results.tracks[0]
            player.add(requester=ctx.author.id, track=track)

            src = get_source_emoji_from_uri(track.uri)

            if player.is_playing:
                # Show enqueued
                layout = ui.LayoutView()
                container = ui.Container(accent_colour=None)
                container.add_item(ui.TextDisplay(f"### {emojis.SUCCESS} Enqueued"))
                container.add_item(ui.Separator())

                info = (
                    f"### {src} [{track.title}]({track.uri})\n"
                    f"{emojis.DOT} **Artist:** {track.author}\n"
                    f"{emojis.DOT} **Duration:** `{format_duration(track.duration)}`\n"
                    f"{emojis.DOT} **Position:** `{len(player.queue)}`\n"
                    f"{emojis.DOT} **Requester:** {ctx.author.mention}"
                )
                thumb = self._get_thumbnail(track)
                if thumb:
                    try:
                        section = ui.Section(accessory=make_thumbnail(thumb))
                        section.add_item(ui.TextDisplay(info))
                        container.add_item(section)
                    except Exception as e:
                        print(f"[Enqueue Thumbnail Error] {e}")
                        container.add_item(ui.TextDisplay(info))
                else:
                    container.add_item(ui.TextDisplay(info))
                layout.add_item(container)
                await loading_msg.edit(view=layout)
            else:
                try:
                    await loading_msg.delete()
                except discord.HTTPException:
                    pass

        # Start playback
        if not player.is_playing:
            try:
                await player.play()
            except Exception as e:
                print(f"[Play] {e}")
                view = make_text_container(f"{emojis.ERROR} Playback failed: `{e}`")
                await ctx.send(view=view)

    @commands.hybrid_command(name="join", aliases=["connect"])
    @commands.guild_only()
    async def join(self, ctx, *, channel: discord.VoiceChannel = None):
        """Connect to a voice channel."""
        if not channel:
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await ctx.reply(view=make_text_container(f"{emojis.ERROR} You must be in a voice channel or specify one."))
            channel = ctx.author.voice.channel

        player = self.lavalink.player_manager.create(ctx.guild.id)
        
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.connect or not perms.speak:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} I need Connect and Speak permissions in `{channel.name}`."))

        if ctx.guild.voice_client:
            if ctx.guild.voice_client.channel == channel:
                return await ctx.reply(view=make_text_container(f"{emojis.INFO} Already connected to `{channel.name}`."))
            player.store("channel", ctx.channel.id)
            await ctx.guild.voice_client.move_to(channel)
            await self.bot.db.set_247_channel(ctx.guild.id, channel.id)
            return await ctx.reply(view=make_text_container(f"{emojis.SUCCESS} Moved to voice channel **{channel.name}**."))

        player.store("channel", ctx.channel.id)
        await channel.connect(cls=LavalinkVoiceClient, self_deaf=True)
        is_247 = await self.bot.db.get_247(ctx.guild.id)
        if is_247:
            await self.bot.db.set_247_channel(ctx.guild.id, channel.id)
            
        await ctx.reply(view=make_text_container(f"{emojis.SUCCESS} Connected to voice channel **{channel.name}**."))

    @commands.hybrid_command(name="move")
    @commands.guild_only()
    async def move(self, ctx, *, channel: discord.VoiceChannel = None):
        """Move the bot to another voice channel."""
        if not ctx.guild.voice_client:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} I am not connected to any voice channel. Use `/join` instead."))

        if not channel:
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await ctx.reply(view=make_text_container(f"{emojis.ERROR} You must be in a voice channel or specify one to move me."))
            channel = ctx.author.voice.channel

        if ctx.guild.voice_client.channel == channel:
            return await ctx.reply(view=make_text_container(f"{emojis.INFO} Already in `{channel.name}`."))

        perms = channel.permissions_for(ctx.guild.me)
        if not perms.connect or not perms.speak:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} I need Connect and Speak permissions in `{channel.name}`."))

        player = self.lavalink.player_manager.create(ctx.guild.id)
        player.store("channel", ctx.channel.id)
        await ctx.guild.voice_client.move_to(channel)
        
        is_247 = await self.bot.db.get_247(ctx.guild.id)
        if is_247:
            await self.bot.db.set_247_channel(ctx.guild.id, channel.id)

        await ctx.reply(view=make_text_container(f"{emojis.SUCCESS} Moved to voice channel **{channel.name}**."))

    @commands.hybrid_command(name="dc", aliases=["leave", "disconnect"])
    @commands.guild_only()
    async def dc_cmd(self, ctx):
        """Disconnect the bot from voice."""
        player = self.lavalink.player_manager.get(ctx.guild.id) if self.lavalink else None
        if player:
            self._last_announced.pop(ctx.guild.id, None)
            player.queue.clear()
            await player.stop()

        await self._clear_vc_status(ctx.guild.id)

        if ctx.guild.voice_client:
            await ctx.guild.voice_client.disconnect(force=True)

        await self._notify_dashboard(ctx.guild.id)

        msg = self.now_playing_messages.pop(ctx.guild.id, None)
        if msg:
            try:
                await msg.delete()
            except discord.HTTPException:
                pass

        view = make_text_container(f"{emojis.ERROR} Disconnected from voice channel.")
        await ctx.reply(view=view)

    @commands.hybrid_command(name="rejoin")
    @commands.guild_only()
    async def rejoin(self, ctx):
        """Disconnect and reconnect to the voice channel."""
        vc = ctx.guild.voice_client
        if not vc or not vc.channel:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} I am not connected to any voice channel."))

        channel = vc.channel
        player = self.lavalink.player_manager.get(ctx.guild.id)
        bound_channel = player.fetch("channel") if player else None
        
        try:
            await vc.disconnect(force=True)
        except Exception:
            pass

        await asyncio.sleep(1.0)

        try:
            player = self.lavalink.player_manager.create(ctx.guild.id)
            if bound_channel:
                player.store("channel", bound_channel)
            await channel.connect(cls=LavalinkVoiceClient, self_deaf=True)
            
            is_247 = await self.bot.db.get_247(ctx.guild.id)
            if is_247:
                await self.bot.db.set_247_channel(ctx.guild.id, channel.id)

            await ctx.reply(view=make_text_container(f"{emojis.SUCCESS} Successfully rejoined voice channel **{channel.name}**."))
        except Exception as e:
            await ctx.reply(view=make_text_container(f"{emojis.ERROR} Failed to reconnect to `{channel.name}`: `{e}`"))

    @commands.hybrid_command(name="skip", aliases=["s"])
    @commands.guild_only()
    async def skip(self, ctx):
        """Skip current track."""
        player = self.lavalink.player_manager.get(ctx.guild.id) if self.lavalink else None
        if not player or not player.is_playing:
            view = make_text_container(f"{emojis.ERROR} Nothing is playing.")
            return await ctx.reply(view=view)
        await player.skip()
        await self._notify_dashboard(ctx.guild.id)
        view = make_text_container(f"{emojis.BTN_SKIP} Skipped.")
        await ctx.reply(view=view)

    @commands.hybrid_command(name="stop")
    @commands.guild_only()
    async def stop(self, ctx):
        """Stop playback and clear queue without disconnecting."""
        player = self.lavalink.player_manager.get(ctx.guild.id) if self.lavalink else None
        if not player:
            view = make_text_container(f"{emojis.ERROR} Not connected.")
            return await ctx.reply(view=view)

        self._last_announced.pop(ctx.guild.id, None)
        player.queue.clear()
        await player.stop()

        # Start idle timer if 24/7 is disabled
        is_247 = await self.bot.db.get_247(ctx.guild.id)
        if not is_247:
            self._start_idle_timer(ctx.guild.id)

        await self._notify_dashboard(ctx.guild.id)

        msg = self.now_playing_messages.pop(ctx.guild.id, None)
        if msg:
            try:
                await msg.delete()
            except discord.HTTPException:
                pass

        view = make_text_container(f"{emojis.BTN_STOP} Playback stopped and queue cleared.")
        await ctx.reply(view=view)

    @commands.hybrid_command(name="pause")
    @commands.guild_only()
    async def pause(self, ctx):
        """Pause player."""
        player = self.lavalink.player_manager.get(ctx.guild.id) if self.lavalink else None
        if not player or not player.is_playing:
            view = make_text_container(f"{emojis.ERROR} Nothing is playing.")
            return await ctx.reply(view=view)
        await player.set_pause(True)
        await self._update_now_playing(ctx.guild.id)
        await self._notify_dashboard(ctx.guild.id)
        view = make_text_container(f"{emojis.BTN_PAUSE} Paused.")
        await ctx.reply(view=view)

    @commands.hybrid_command(name="resume", aliases=["unpause"])
    @commands.guild_only()
    async def resume(self, ctx):
        """Resume player."""
        player = self.lavalink.player_manager.get(ctx.guild.id) if self.lavalink else None
        if not player:
            view = make_text_container(f"{emojis.ERROR} Nothing to resume.")
            return await ctx.reply(view=view)
        await player.set_pause(False)
        await self._update_now_playing(ctx.guild.id)
        await self._notify_dashboard(ctx.guild.id)
        view = make_text_container(f"{emojis.BTN_RESUME} Resumed.")
        await ctx.reply(view=view)

    @commands.hybrid_command(name="volume", aliases=["vol"])
    @commands.guild_only()
    async def volume(self, ctx, vol: int = None):
        """Set/view volume."""
        player = self.lavalink.player_manager.get(ctx.guild.id) if self.lavalink else None
        if not player:
            view = make_text_container(f"{emojis.ERROR} Not connected.")
            return await ctx.reply(view=view)
        if vol is None:
            view = make_text_container(f"Current volume: `{player.volume}%`")
            return await ctx.reply(view=view)
        vol = max(0, min(150, vol))
        await player.set_volume(vol)
        await self._notify_dashboard(ctx.guild.id)
        view = make_text_container(f"{emojis.SUCCESS} Volume set to `{vol}%`")
        await ctx.reply(view=view)

    @commands.hybrid_command(name="loop", aliases=["repeat"])
    @commands.guild_only()
    async def loop(self, ctx):
        """Toggle loop."""
        player = self.lavalink.player_manager.get(ctx.guild.id) if self.lavalink else None
        if not player or not player.is_playing:
            view = make_text_container(f"{emojis.ERROR} Nothing is playing.")
            return await ctx.reply(view=view)
        player.set_loop(0 if player.loop else 1)
        await self._update_now_playing(ctx.guild.id)
        await self._notify_dashboard(ctx.guild.id)
        state = "enabled" if player.loop else "disabled"
        view = make_text_container(f"{emojis.BTN_LOOP} Loop **{state}**.")
        await ctx.reply(view=view)

    @commands.hybrid_command(name="shuffle")
    @commands.guild_only()
    async def shuffle(self, ctx):
        """Shuffle queue."""
        player = self.lavalink.player_manager.get(ctx.guild.id) if self.lavalink else None
        if not player or not player.queue:
            view = make_text_container(f"{emojis.ERROR} Queue is empty.")
            return await ctx.reply(view=view)
        random.shuffle(player.queue)
        view = make_text_container(f"{emojis.SUCCESS} Queue shuffled!")
        await ctx.reply(view=view)
        await self._notify_dashboard(ctx.guild.id)

    async def play_previous(self, guild_id: int) -> bool:
        """Re-queue the previous track and skip to it. Used by both the
        `>previous` command and the dashboard's Previous button."""
        player = self.lavalink.player_manager.get(guild_id) if self.lavalink else None
        hist = self.history.get(guild_id, [])
        if not player or len(hist) < 2:
            return False
        # hist[-1] is the current track; hist[-2] is the one before it.
        prev_track = hist[-2]
        hist.pop()  # drop current so it isn't immediately re-picked as "previous" again
        player.queue.insert(0, prev_track)
        await player.skip()
        return True

    @commands.hybrid_command(name="previous", aliases=["prev", "back"])
    @commands.guild_only()
    async def previous(self, ctx):
        """Play the previous track."""
        ok = await self.play_previous(ctx.guild.id)
        if not ok:
            view = make_text_container(f"{emojis.ERROR} No previous track.")
            return await ctx.reply(view=view)
        view = make_text_container(f"{emojis.SUCCESS} Playing previous track.")
        await ctx.reply(view=view)
        await self._notify_dashboard(ctx.guild.id)

    @commands.hybrid_command(name="replay")
    @commands.guild_only()
    async def replay(self, ctx):
        """Restart the current track from the beginning."""
        player = self.lavalink.player_manager.get(ctx.guild.id) if self.lavalink else None
        if not player or not player.current:
            view = make_text_container(f"{emojis.ERROR} Nothing is playing.")
            return await ctx.reply(view=view)
        await player.seek(0)
        view = make_text_container(f"{emojis.SUCCESS} Replaying current track.")
        await ctx.reply(view=view)
        await self._notify_dashboard(ctx.guild.id)

    @commands.hybrid_command(name="queue", aliases=["q"])
    @commands.guild_only()
    async def queue_cmd(self, ctx):
        """Show queue."""
        player = self.lavalink.player_manager.get(ctx.guild.id) if self.lavalink else None
        if not player or (not player.queue and not player.current):
            view = make_text_container(f"{emojis.ERROR} Queue is empty.")
            return await ctx.reply(view=view)

        desc = ""
        total = 0
        for i, track in enumerate(list(player.queue)[:15]):
            src = get_source_emoji_from_uri(track.uri)
            desc += f"`{i+1}.` {src} **{truncate(track.title, 35)}** — `{format_duration(track.duration)}`\n"
            total += track.duration

        text = f"### {emojis.MUSIC} Queue\n{desc}"
        text += f"\n-# {len(player.queue)} tracks | Total: {format_duration(total)}"
        if len(player.queue) > 15:
            text += f"\n-# And `{len(player.queue) - 15}` more..."
        view = make_text_container(text)
        await ctx.reply(view=view)

    @commands.hybrid_command(name="nowplaying", aliases=["np"])
    @commands.guild_only()
    async def nowplaying(self, ctx):
        """Show now playing."""
        player = self.lavalink.player_manager.get(ctx.guild.id) if self.lavalink else None
        if not player or not player.current:
            view = make_text_container(f"{emojis.ERROR} Nothing is playing.")
            return await ctx.reply(view=view)
        layout = NowPlayingLayout(self, ctx.guild.id)
        layout.build(player)
        msg = await ctx.reply(view=layout)
        layout.message = msg
        self.now_playing_messages[ctx.guild.id] = msg

    @commands.hybrid_command(name="autoplay", aliases=["ap"])
    @commands.guild_only()
    async def autoplay_cmd(self, ctx):
        """Toggle autoplay."""
        current = self.autoplay_states.get(ctx.guild.id, False)
        self.autoplay_states[ctx.guild.id] = not current
        status = "Enabled" if not current else "Disabled"
        view = make_text_container(f"{emojis.BTN_AUTOPLAY} Autoplay: **{status}**")
        await ctx.reply(view=view)
        await self._update_now_playing(ctx.guild.id)
        await self._notify_dashboard(ctx.guild.id)


async def setup(bot):
    await bot.add_cog(Music(bot))