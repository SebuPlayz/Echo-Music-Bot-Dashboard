import discord
from discord.ext import commands
from discord import ui
import emojis
import time
import asyncio
from cogs.music import get_source_emoji_from_uri, format_duration, LavalinkVoiceClient

def make_text_container(text: str) -> ui.LayoutView:
    view = ui.LayoutView()
    container = ui.Container(accent_colour=None)
    container.add_item(ui.TextDisplay(text))
    view.add_item(container)
    return view

class Playlist(commands.Cog, name="Playlist"):
    """Playlist commands — manage custom user playlists."""

    def __init__(self, bot):
        self.bot = bot

    # Base commands
    @commands.hybrid_group(name="playlist", aliases=["pl"], invoke_without_command=True)
    @commands.guild_only()
    async def playlist_group(self, ctx):
        """Playlist commands group."""
        text = (
            f"### {emojis.CAT_MUSIC} Playlist Commands\n"
            f"Manage and play your custom playlists.\n\n"
            f"{emojis.DOT} `{ctx.prefix}playlist create <name>`\n"
            f"{emojis.DOT} `{ctx.prefix}playlist delete <name>`\n"
            f"{emojis.DOT} `{ctx.prefix}playlist rename <old_name> <new_name>`\n"
            f"{emojis.DOT} `{ctx.prefix}playlist list`\n"
            f"{emojis.DOT} `{ctx.prefix}playlist show <name>`\n"
            f"{emojis.DOT} `{ctx.prefix}playlist add <name> [song]`\n"
            f"{emojis.DOT} `{ctx.prefix}playlist remove <name> <song_index>`\n"
            f"{emojis.DOT} `{ctx.prefix}playlist public <name>`\n"
            f"{emojis.DOT} `{ctx.prefix}playlist private <name>`\n"
            f"{emojis.DOT} `{ctx.prefix}playlist play <name>`\n"
            f"{emojis.DOT} `{ctx.prefix}playlist playcode <code>`"
        )
        await ctx.reply(view=make_text_container(text))

    @playlist_group.command(name="create")
    @commands.guild_only()
    async def create_pl(self, ctx, *, name: str):
        """Create a new playlist."""
        name = name.strip()
        if not name:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Name cannot be empty."))
        
        # Check if already exists
        existing = await self.bot.db.get_playlist_by_name(ctx.author.id, name)
        if existing:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} A playlist named `{name}` already exists."))

        await self.bot.db.create_playlist(ctx.author.id, name)
        await ctx.reply(view=make_text_container(f"{emojis.SUCCESS} Created playlist **{name}**!"))

    @playlist_group.command(name="delete")
    @commands.guild_only()
    async def delete_pl(self, ctx, *, name: str):
        """Delete an existing playlist."""
        name = name.strip()
        existing = await self.bot.db.get_playlist_by_name(ctx.author.id, name)
        if not existing:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Playlist `{name}` not found."))

        playlist_id = existing[0]
        await self.bot.db.delete_playlist(ctx.author.id, playlist_id)
        await ctx.reply(view=make_text_container(f"{emojis.SUCCESS} Deleted playlist **{name}**."))

    @playlist_group.command(name="rename")
    @commands.guild_only()
    async def rename_pl(self, ctx, old_name: str, new_name: str):
        """Rename an existing playlist."""
        old_name = old_name.strip()
        new_name = new_name.strip()
        
        existing = await self.bot.db.get_playlist_by_name(ctx.author.id, old_name)
        if not existing:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Playlist `{old_name}` not found."))
            
        # Check if new name already exists
        conflict = await self.bot.db.get_playlist_by_name(ctx.author.id, new_name)
        if conflict:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} A playlist named `{new_name}` already exists."))

        playlist_id = existing[0]
        await self.bot.db.rename_playlist(ctx.author.id, playlist_id, new_name)
        await ctx.reply(view=make_text_container(f"{emojis.SUCCESS} Renamed playlist **{old_name}** to **{new_name}**."))

    @playlist_group.command(name="list")
    @commands.guild_only()
    async def list_pls(self, ctx):
        """List all your playlists."""
        playlists = await self.bot.db.get_playlists(ctx.author.id)
        if not playlists:
            return await ctx.reply(view=make_text_container(f"{emojis.INFO} You don't have any playlists yet. Create one with `{ctx.prefix}playlist create <name>`."))

        desc = ""
        for p in playlists:
            desc += f"{emojis.DOT} **{p[1]}** — `{p[3]}` tracks\n"
        
        text = f"### {emojis.MYMUSIC} Your Playlists\n{desc}"
        await ctx.reply(view=make_text_container(text))

    @playlist_group.command(name="show")
    @commands.guild_only()
    async def show_pl(self, ctx, *, name: str):
        """Show tracks inside a playlist."""
        name = name.strip()
        existing = await self.bot.db.get_playlist_by_name(ctx.author.id, name)
        if not existing:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Playlist `{name}` not found."))

        playlist_id, pl_name, _ = existing
        tracks = await self.bot.db.get_playlist_tracks(playlist_id)
        if not tracks:
            return await ctx.reply(view=make_text_container(f"{emojis.INFO} Playlist **{pl_name}** is empty."))

        desc = ""
        for i, t in enumerate(tracks[:20]):
            src = get_source_emoji_from_uri(t[3])
            desc += f"`{i+1}.` {src} **{t[1]}**\n"
            
        text = f"### {emojis.MUSIC} Playlist: {pl_name}\n{desc}"
        if len(tracks) > 20:
            text += f"\n-# And `{len(tracks) - 20}` more..."
        await ctx.reply(view=make_text_container(text))

    @playlist_group.command(name="add")
    @commands.guild_only()
    async def add_to_pl(self, ctx, name: str, *, query: str = None):
        """Add a song to a playlist. Defaults to currently playing song."""
        name = name.strip()
        existing = await self.bot.db.get_playlist_by_name(ctx.author.id, name)
        if not existing:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Playlist `{name}` not found."))

        playlist_id, pl_name, _ = existing
        music_cog = self.bot.get_cog("Music")

        # If query is not specified, get currently playing track
        if not query:
            if not music_cog or not music_cog.lavalink:
                return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Music system is not available."))
            player = music_cog.lavalink.player_manager.get(ctx.guild.id)
            if not player or not player.current:
                return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Nothing is currently playing in this server. Please specify a song name or URL to add."))
            track = player.current
            await self.bot.db.add_to_playlist(playlist_id, track.title, track.author, track.uri, track.identifier)
            return await ctx.reply(view=make_text_container(f"{emojis.SUCCESS} Added **{track.title}** to playlist **{pl_name}**!"))

        # Otherwise, search and add
        if not music_cog or not music_cog.lavalink:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Music system is not available."))
        player = music_cog.lavalink.player_manager.create(ctx.guild.id)
        search_query = query.strip()
        if not (search_query.startswith("http://") or search_query.startswith("https://")):
            search_query = f"ytsearch:{search_query}"
        
        loading_msg = await ctx.reply(view=make_text_container(f"{emojis.LOADING} Searching song..."))
        try:
            results = await player.node.get_tracks(search_query)
            if not results or not results.tracks:
                return await loading_msg.edit(view=make_text_container(f"{emojis.ERROR} No results found for **{query}**."))
            track = results.tracks[0]
            await self.bot.db.add_to_playlist(playlist_id, track.title, track.author, track.uri, track.identifier)
            await loading_msg.edit(view=make_text_container(f"{emojis.SUCCESS} Added **{track.title}** to playlist **{pl_name}**!"))
        except Exception as e:
            await loading_msg.edit(view=make_text_container(f"{emojis.ERROR} Failed to add track: `{e}`"))

    @playlist_group.command(name="remove")
    @commands.guild_only()
    async def remove_from_pl(self, ctx, name: str, index: int):
        """Remove a song from a playlist by its index (shown in show command)."""
        name = name.strip()
        existing = await self.bot.db.get_playlist_by_name(ctx.author.id, name)
        if not existing:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Playlist `{name}` not found."))

        playlist_id, pl_name, _ = existing
        tracks = await self.bot.db.get_playlist_tracks(playlist_id)
        if not tracks:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Playlist **{pl_name}** is empty."))

        if index < 1 or index > len(tracks):
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Invalid index. Use `{ctx.prefix}playlist show {pl_name}` to see the indices."))

        track_to_remove = tracks[index - 1]
        track_id = track_to_remove[0]
        track_title = track_to_remove[1]
        
        await self.bot.db.remove_from_playlist(playlist_id, track_id)
        await ctx.reply(view=make_text_container(f"{emojis.SUCCESS} Removed **{track_title}** from playlist **{pl_name}**."))

    @playlist_group.command(name="public")
    @commands.guild_only()
    async def public_pl(self, ctx, *, name: str):
        """Set a playlist to public."""
        name = name.strip()
        existing = await self.bot.db.get_playlist_by_name(ctx.author.id, name)
        if not existing:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Playlist `{name}` not found."))
            
        playlist_id = existing[0]
        await self.bot.db.set_playlist_privacy(ctx.author.id, playlist_id, True)
        code = await self.bot.db.ensure_playlist_code(playlist_id)
        await ctx.reply(view=make_text_container(
            f"{emojis.SUCCESS} Playlist **{name}** is now **Public**!\n"
            f"Share code: `{code}`"
        ))

    @playlist_group.command(name="private")
    @commands.guild_only()
    async def private_pl(self, ctx, *, name: str):
        """Set a playlist to private."""
        name = name.strip()
        existing = await self.bot.db.get_playlist_by_name(ctx.author.id, name)
        if not existing:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Playlist `{name}` not found."))
            
        playlist_id = existing[0]
        await self.bot.db.set_playlist_privacy(ctx.author.id, playlist_id, False)
        await ctx.reply(view=make_text_container(f"{emojis.SUCCESS} Playlist **{name}** is now **Private**."))

    @playlist_group.command(name="playcode", aliases=["code"])
    @commands.guild_only()
    async def playcode_pl(self, ctx, code: str):
        """Play a public playlist by its share code."""
        code = code.strip().upper()
        if not code:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Please specify a playlist share code."))

        playlist = await self.bot.db.get_playlist_by_code(code)
        if not playlist:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} No public playlist found with code `{code}`."))

        playlist_id, pl_name, owner_id, track_count, is_public, _ = playlist
        
        is_owner = ctx.author.id == owner_id
        if not is_public and not is_owner:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} This playlist is private."))

        tracks = await self.bot.db.get_playlist_tracks(playlist_id)
        if not tracks:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Playlist **{pl_name}** is empty."))

        music_cog = self.bot.get_cog("Music")
        if not music_cog:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Music system is not available."))

        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} You must be in a voice channel."))

        vc = ctx.author.voice.channel
        player = music_cog.lavalink.player_manager.create(ctx.guild.id)

        if not ctx.guild.voice_client:
            perms = vc.permissions_for(ctx.guild.me)
            if not perms.connect or not perms.speak:
                return await ctx.reply(view=make_text_container(f"{emojis.ERROR} I need Connect and Speak permissions in your voice channel."))
            player.store("channel", ctx.channel.id)
            try:
                await vc.connect(cls=LavalinkVoiceClient, self_deaf=True)
                await asyncio.sleep(0.5)
            except Exception as e:
                return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Failed to connect: `{e}`"))
        elif ctx.guild.voice_client.channel != vc:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} You must be in my voice channel."))

        loading_msg = await ctx.reply(view=make_text_container(f"{emojis.LOADING} Loading tracks from playlist **{pl_name}**..."))

        added_count = 0
        for t in tracks:
            track_title = t[1]
            track_uri = t[3]
            search_query = track_uri if track_uri else f"ytsearch:{track_title}"
            try:
                results = await player.node.get_tracks(search_query)
                if results and results.tracks:
                    player.add(requester=ctx.author.id, track=results.tracks[0])
                    added_count += 1
            except Exception as e:
                print(f"[PlayCodeCog] Exception while adding track '{track_title}': {e}")

        if added_count == 0:
            return await loading_msg.edit(view=make_text_container(f"{emojis.ERROR} Failed to load any songs from the playlist."))

        if not player.is_playing:
            try:
                await player.play()
            except Exception as e:
                return await loading_msg.edit(view=make_text_container(f"{emojis.ERROR} Playback failed: `{e}`"))

        await self.bot.db.record_playlist_play(playlist_id)
        await music_cog._notify_dashboard(ctx.guild.id)
        await loading_msg.edit(view=make_text_container(f"{emojis.SUCCESS} Enqueued `{added_count}` tracks from playlist **{pl_name}**!"))

    @playlist_group.command(name="play")
    @commands.guild_only()
    async def play_pl(self, ctx, *, name: str):
        """Play a custom playlist."""
        name = name.strip()
        existing = await self.bot.db.get_playlist_by_name(ctx.author.id, name)
        if not existing:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Playlist `{name}` not found."))

        playlist_id, pl_name, _ = existing
        tracks = await self.bot.db.get_playlist_tracks(playlist_id)
        if not tracks:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Playlist **{pl_name}** is empty."))

        music_cog = self.bot.get_cog("Music")
        if not music_cog:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Music system is not available."))

        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} You must be in a voice channel."))

        vc = ctx.author.voice.channel
        player = music_cog.lavalink.player_manager.create(ctx.guild.id)

        if not ctx.guild.voice_client:
            perms = vc.permissions_for(ctx.guild.me)
            if not perms.connect or not perms.speak:
                return await ctx.reply(view=make_text_container(f"{emojis.ERROR} I need Connect and Speak permissions in your voice channel."))
            player.store("channel", ctx.channel.id)
            try:
                await vc.connect(cls=LavalinkVoiceClient, self_deaf=True)
                await asyncio.sleep(0.5)
            except Exception as e:
                return await ctx.reply(view=make_text_container(f"{emojis.ERROR} Failed to connect: `{e}`"))
        elif ctx.guild.voice_client.channel != vc:
            return await ctx.reply(view=make_text_container(f"{emojis.ERROR} You must be in my voice channel."))

        loading_msg = await ctx.reply(view=make_text_container(f"{emojis.LOADING} Loading tracks from playlist **{pl_name}**..."))

        added_count = 0
        for t in tracks:
            track_title = t[1]
            track_uri = t[3]
            search_query = track_uri if track_uri else f"ytsearch:{track_title}"
            print(f"[PlayPlaylistCog] Searching track: '{track_title}' with query: '{search_query}'")
            try:
                results = await player.node.get_tracks(search_query)
                if results and results.tracks:
                    player.add(requester=ctx.author.id, track=results.tracks[0])
                    added_count += 1
                    print(f"[PlayPlaylistCog] Successfully added track: '{results.tracks[0].title}'")
                else:
                    print(f"[PlayPlaylistCog] No results found for query: '{search_query}'")
            except Exception as e:
                print(f"[PlayPlaylistCog] Exception while adding track '{track_title}': {e}")

        if added_count == 0:
            return await loading_msg.edit(view=make_text_container(f"{emojis.ERROR} Failed to load any songs from the playlist."))

        if not player.is_playing:
            try:
                await player.play()
            except Exception as e:
                return await loading_msg.edit(view=make_text_container(f"{emojis.ERROR} Playback failed: `{e}`"))

        await self.bot.db.record_playlist_play(playlist_id)
        await music_cog._notify_dashboard(ctx.guild.id)
        await loading_msg.edit(view=make_text_container(f"{emojis.SUCCESS} Enqueued `{added_count}` tracks from playlist **{pl_name}**!"))

async def setup(bot):
    await bot.add_cog(Playlist(bot))
