"""
Lets the bot owner grant specific users the ability to run commands
without typing the server prefix. Only fires for real command names,
so normal chat is never touched.
"""

import discord
from discord.ext import commands
from discord import ui
import time

import emojis
from config import Config


def make_text_container(text: str) -> ui.LayoutView:
    view = ui.LayoutView()
    container = ui.Container(accent_colour=None)
    container.add_item(ui.TextDisplay(text))
    view.add_item(container)
    return view


DURATION_MAP = {
    "1h": 3600,
    "1d": 86400,
    "7d": 604800,
    "30d": 2592000,
    "lifetime": None,
}


class NoPrefix(commands.Cog, name="NoPrefix"):
    """Owner-only NoPrefix management. Hidden from the public help menu."""

    def __init__(self, bot):
        self.bot = bot

    def _looks_like_command(self, content: str) -> bool:
        """True only if the first word matches a real registered command/alias."""
        if not content:
            return False
        first_word = content.split(maxsplit=1)[0].lower()
        if not first_word:
            return False
        return self.bot.get_command(first_word) is not None

    # ── Smart NoPrefix execution ──────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # If this is already a valid prefixed/mention command, let the
        # normal dispatch handle it — never double-invoke.
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        content = message.content.strip()
        if not content:
            return

        # If it already starts with a real prefix, leave it alone
        # (it just didn't resolve to a command — not our job).
        try:
            prefixes = await self.bot._get_prefix(self.bot, message)
        except Exception:
            prefixes = [Config.DEFAULT_PREFIX]
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        for p in prefixes:
            if isinstance(p, str) and content.startswith(p):
                return

        if not self._looks_like_command(content):
            return  # plain chat — ignore entirely, zero overhead

        is_owner = await self.bot.is_owner(message.author)
        if not is_owner and not await self.bot.db.is_noprefix(message.author.id):
            return  # not a granted user — ignore

        # Get server's prefix to use for parsing
        try:
            prefixes = await self.bot._get_prefix(self.bot, message)
        except Exception:
            prefixes = [Config.DEFAULT_PREFIX]
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        prefix = Config.DEFAULT_PREFIX
        for p in prefixes:
            if p and isinstance(p, str):
                prefix = p
                break

        # Dispatch manually using a synthetic copy of message with the prefix prepended
        # so discord.py can natively parse subcommands and arguments correctly.
        import copy
        fake_message = copy.copy(message)
        fake_message.content = prefix + content
        new_ctx = await self.bot.get_context(fake_message)
        new_ctx.prefix = ""  # keep prefix displayed as empty for noprefix output
        
        if new_ctx.command is None:
            return
        try:
            await self.bot.invoke(new_ctx)
        except Exception as e:
            print(f"[NoPrefix] dispatch error for {message.author.id}: {e}")

    # ── Owner commands ───────────────────────────────────────────

    @commands.group(name="noprefix", aliases=["nop"], invoke_without_command=True, hidden=True)
    @commands.is_owner()
    async def noprefix(self, ctx):
        text = (
            f"### {emojis.CROWN} NoPrefix Management\n"
            f"{emojis.DOT} `{ctx.prefix}noprefix add @user [1h/1d/7d/30d/lifetime]`\n"
            f"{emojis.DOT} `{ctx.prefix}noprefix remove @user`\n"
            f"{emojis.DOT} `{ctx.prefix}noprefix list`\n"
            f"{emojis.DOT} `{ctx.prefix}noprefix check @user`"
        )
        await ctx.reply(view=make_text_container(text))

    @noprefix.command(name="add", hidden=True)
    @commands.is_owner()
    async def noprefix_add(self, ctx, member: discord.Member, duration: str = "lifetime"):
        duration = duration.lower()
        if duration not in DURATION_MAP:
            view = make_text_container(
                f"{emojis.ERROR} Invalid duration. Use one of: `1h`, `1d`, `7d`, `30d`, `lifetime`."
            )
            return await ctx.reply(view=view)

        seconds = DURATION_MAP[duration]
        expires_at = int(time.time()) + seconds if seconds else None

        await self.bot.db.add_noprefix(member.id, ctx.author.id, expires_at)

        expiry_text = "Never (Lifetime)" if expires_at is None else f"<t:{expires_at}:R>"
        view = make_text_container(
            f"### {emojis.SUCCESS} NoPrefix Granted\n"
            f"{emojis.DOT} **User:** {member.mention}\n"
            f"{emojis.DOT} **Expires:** {expiry_text}\n"
            f"{emojis.DOT} **Granted by:** {ctx.author.mention}"
        )
        await ctx.reply(view=view)

        try:
            dm_text = (
                f"### {emojis.GIFT} You've been granted NoPrefix!\n"
                f"{emojis.DOT} You can now use commands without typing a prefix.\n"
                f"{emojis.DOT} **Expires:** {expiry_text}"
            )
            await member.send(view=make_text_container(dm_text))
        except Exception:
            pass

    @noprefix.command(name="remove", hidden=True)
    @commands.is_owner()
    async def noprefix_remove(self, ctx, member: discord.Member):
        existed = await self.bot.db.remove_noprefix(member.id)
        if not existed:
            view = make_text_container(f"{emojis.ERROR} {member.mention} doesn't have NoPrefix.")
            return await ctx.reply(view=view)

        view = make_text_container(f"{emojis.SUCCESS} Removed NoPrefix from {member.mention}.")
        await ctx.reply(view=view)

    @noprefix.command(name="check", hidden=True)
    @commands.is_owner()
    async def noprefix_check(self, ctx, member: discord.Member):
        row = await self.bot.db.get_noprefix(member.id)
        if not row or not await self.bot.db.is_noprefix(member.id):
            view = make_text_container(f"{emojis.INFO} {member.mention} doesn't have active NoPrefix.")
            return await ctx.reply(view=view)

        _, added_by, added_at, expires_at = row
        expiry_text = "Never (Lifetime)" if expires_at is None else f"<t:{expires_at}:R>"
        granter = ctx.guild.get_member(added_by)
        granter_text = granter.mention if granter else f"`{added_by}`"

        view = make_text_container(
            f"### {emojis.INFO} NoPrefix Status\n"
            f"{emojis.DOT} **User:** {member.mention}\n"
            f"{emojis.DOT} **Granted by:** {granter_text}\n"
            f"{emojis.DOT} **Granted:** <t:{added_at}:R>\n"
            f"{emojis.DOT} **Expires:** {expiry_text}"
        )
        await ctx.reply(view=view)

    @noprefix.command(name="list", hidden=True)
    @commands.is_owner()
    async def noprefix_list(self, ctx):
        rows = await self.bot.db.list_noprefix()
        if not rows:
            view = make_text_container(f"{emojis.INFO} No users have NoPrefix.")
            return await ctx.reply(view=view)

        lines = []
        for user_id, added_by, added_at, expires_at in rows:
            expiry_text = "Lifetime" if expires_at is None else f"<t:{expires_at}:R>"
            lines.append(f"{emojis.DOT} <@{user_id}> — expires {expiry_text}")

        text = f"### {emojis.LIST_ICO} NoPrefix Users ({len(rows)})\n" + "\n".join(lines[:25])
        await ctx.reply(view=make_text_container(text))


async def setup(bot):
    await bot.add_cog(NoPrefix(bot))
