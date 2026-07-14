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


class TwoFourSevenLayout(ui.LayoutView):
    def __init__(self, bot, ctx, current):
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.current = current
        self.message = None
        self.rebuild()

    def rebuild(self):
        self.clear_items()
        container = ui.Container(accent_colour=None)

        status = "Enabled" if self.current else "Disabled"
        container.add_item(ui.TextDisplay(f"### 24/7 Mode"))
        container.add_item(ui.Separator())
        container.add_item(ui.TextDisplay(
            f"{emojis.DOT} **Status:** `{status}`\n"
            f"{emojis.DOT} **Action by:** {self.ctx.author.mention}\n\n"
            f"When enabled, I won't auto-disconnect from voice."
        ))
        container.add_item(ui.Separator())

        row = ui.ActionRow()
        enable_style = discord.ButtonStyle.success if not self.current else discord.ButtonStyle.secondary
        disable_style = discord.ButtonStyle.danger if self.current else discord.ButtonStyle.secondary

        enable_btn = ToggleBtn("enable", "Enable", enable_style, self, disabled=self.current)
        disable_btn = ToggleBtn("disable", "Disable", disable_style, self, disabled=not self.current)
        row.add_item(enable_btn)
        row.add_item(disable_btn)
        container.add_item(row)

        self.add_item(container)


class ToggleBtn(ui.Button):
    def __init__(self, action, label, style, layout, disabled=False):
        super().__init__(label=label, style=style, disabled=disabled)
        self.action = action
        self.layout = layout

    async def callback(self, interaction):
        if interaction.user.id != self.layout.ctx.author.id:
            return await interaction.response.send_message("Not for you.", ephemeral=True)
        value = self.action == "enable"
        guild_id = self.layout.ctx.guild.id
        await self.layout.bot.db.set_247(guild_id, value)
        if value:
            vc = self.layout.ctx.guild.voice_client
            if vc and vc.channel:
                await self.layout.bot.db.set_247_channel(guild_id, vc.channel.id)
        self.layout.current = value
        self.layout.rebuild()
        await interaction.response.edit_message(view=self.layout)


class ConfigCog(commands.Cog, name="Config"):
    """Server configuration commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="247")
    @commands.guild_only()
    async def twentyfourseven(self, ctx, channel: discord.VoiceChannel = None):
        """Toggle 24/7 mode or set the 24/7 voice channel."""
        if channel:
            perms = channel.permissions_for(ctx.guild.me)
            if not perms.connect or not perms.speak:
                return await ctx.reply(view=make_text_container(f"{emojis.ERROR} I need Connect and Speak permissions in `{channel.name}`."))
            
            await self.bot.db.set_247(ctx.guild.id, True)
            await self.bot.db.set_247_channel(ctx.guild.id, channel.id)
            return await ctx.reply(view=make_text_container(f"{emojis.SUCCESS} 24/7 mode **Enabled** for voice channel **{channel.name}**!"))

        current = await self.bot.db.get_247(ctx.guild.id)
        layout = TwoFourSevenLayout(self.bot, ctx, current)
        msg = await ctx.reply(view=layout)
        layout.message = msg

    @commands.command(name="setprefix", aliases=["prefix"])
    @commands.has_permissions(manage_guild=True)
    async def setprefix(self, ctx, *, new_prefix: str):
        """Change server prefix."""
        if len(new_prefix) > 5:
            view = make_text_container(f"{emojis.ERROR} Prefix must be 5 chars or less.")
            return await ctx.reply(view=view)
        await self.bot.db.set_prefix(ctx.guild.id, new_prefix)
        text = (
            f"### {emojis.SUCCESS} Prefix Updated\n"
            f"{emojis.DOT} New prefix: `{new_prefix}`\n"
            f"{emojis.DOT} Example: `{new_prefix}play <song>`"
        )
        view = make_text_container(text)
        await ctx.reply(view=view)


async def setup(bot):
    await bot.add_cog(ConfigCog(bot))