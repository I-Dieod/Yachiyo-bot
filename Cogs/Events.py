import discord
from discord.ext import commands

LOG_CH = 1484528280173547582  # 超かぐや姫！ファンサーバー yachiyo-log


class Event(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Logged in as {self.bot.user.name} ({self.bot.user.id})")
        print("Bot is ready!")
        ch = self.bot.get_channel(LOG_CH)
        if ch:
            await ch.send("Bot is ready and running!")

    @commands.command()
    async def ping(self, ctx):
        ch = self.bot.get_channel(LOG_CH)  # 超かぐや姫！ファンサーバー bot-コマンド
        if ch:
            await ch.send("pong")


async def setup(bot: commands.Bot):
    await bot.add_cog(Event(bot))
    print("Event cog loaded successfully.")
    print("Bot is ready to handle events.")
