import discord
from discord.ext import commands
from discord import ui
from config import Config
import emojis


def make_text_container(text: str) -> ui.LayoutView:
    view = ui.LayoutView()
    container = ui.Container(accent_colour=None)
    container.add_item(ui.TextDisplay(text))
    view.add_item(container)
    return view


def make_image_layout(title: str, image_url: str, download_url: str = None) -> ui.LayoutView:
    """Build a layout with title + large image using Section+Thumbnail."""
    layout = ui.LayoutView()
    container = ui.Container(accent_colour=None)
    container.add_item(ui.TextDisplay(f"### {title}"))
    container.add_item(ui.Separator())

    # Use MediaGallery with proper items
    try:
        gallery = ui.MediaGallery()
        gallery.add_item(media=discord.UnfurledMediaItem(url=image_url))
        container.add_item(gallery)
    except Exception:
        # Fallback: use Section with Thumbnail if MediaGallery fails
        section = ui.Section(
            accessory=ui.Thumbnail(media=discord.UnfurledMediaItem(url=image_url))
        )
        section.add_item(ui.TextDisplay(f"[View Full Image]({image_url})"))
        container.add_item(section)

    if download_url:
        container.add_item(ui.Separator())
        row = ui.ActionRow()
        row.add_item(ui.Button(label="Open Image", url=download_url, style=discord.ButtonStyle.link))
        container.add_item(row)

    layout.add_item(container)
    return layout


class Utility(commands.Cog, name="Utility"):
    """Utility commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="avatar", aliases=["av", "pfp"])
    async def avatar(self, ctx, *, member: discord.Member = None):
        """View a user's avatar."""
        m = member or ctx.author
        url = m.display_avatar.with_size(1024).url
        layout = make_image_layout(f"{m.display_name}'s Avatar", url, url)
        await ctx.reply(view=layout)

    @commands.command(name="banner")
    async def banner(self, ctx, *, member: discord.Member = None):
        """View a user's banner."""
        m = member or ctx.author
        user = await self.bot.fetch_user(m.id)
        if not user.banner:
            view = make_text_container(f"{emojis.ERROR} {m.display_name} has no banner.")
            return await ctx.reply(view=view)
        url = user.banner.with_size(1024).url
        layout = make_image_layout(f"{m.display_name}'s Banner", url, url)
        await ctx.reply(view=layout)

    @commands.command(name="servericon", aliases=["sicon"])
    async def servericon(self, ctx):
        """View server icon."""
        if not ctx.guild.icon:
            view = make_text_container(f"{emojis.ERROR} No server icon.")
            return await ctx.reply(view=view)
        url = ctx.guild.icon.with_size(1024).url
        layout = make_image_layout(ctx.guild.name, url, url)
        await ctx.reply(view=layout)

    @commands.command(name="serverbanner", aliases=["sbanner"])
    async def serverbanner(self, ctx):
        """View server banner."""
        if not ctx.guild.banner:
            view = make_text_container(f"{emojis.ERROR} No server banner.")
            return await ctx.reply(view=view)
        url = ctx.guild.banner.with_size(1024).url
        layout = make_image_layout(f"{ctx.guild.name} Banner", url, url)
        await ctx.reply(view=layout)

    @commands.command(name="userinfo", aliases=["ui", "whois"])
    async def userinfo(self, ctx, member: discord.Member = None):
        """View user info."""
        m = member or ctx.author

        text = (
            f"### {m.display_name}\n"
            f"```yaml\n"
            f"Username     : {m}\n"
            f"ID           : {m.id}\n"
            f"Nickname     : {m.nick or 'None'}\n"
            f"Top Role     : {m.top_role.name}\n"
            f"Bot          : {'Yes' if m.bot else 'No'}\n"
            f"Roles        : {len(m.roles) - 1}\n"
            f"```"
        )
        view = make_text_container(text)
        await ctx.reply(view=view)

    @commands.command(name="serverinfo", aliases=["si"])
    async def serverinfo(self, ctx):
        """View server info."""
        g = ctx.guild
        bots = sum(1 for m in g.members if m.bot)
        humans = g.member_count - bots
        text = (
            f"### {g.name}\n"
            f"```yaml\n"
            f"ID           : {g.id}\n"
            f"Owner        : {g.owner}\n"
            f"Members      : {g.member_count}\n"
            f"Humans       : {humans}\n"
            f"Bots         : {bots}\n"
            f"Channels     : {len(g.text_channels) + len(g.voice_channels)}\n"
            f"Roles        : {len(g.roles)}\n"
            f"Boosts       : {g.premium_subscription_count} (Level {g.premium_tier})\n"
            f"```"
        )
        view = make_text_container(text)
        await ctx.reply(view=view)


async def setup(bot):
    await bot.add_cog(Utility(bot))