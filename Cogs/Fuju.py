# Cogs/Fuju.py

import aiomysql
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View


class ButtonList(View):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    @discord.ui.button(label="ふじゅ〜", style=discord.ButtonStyle.primary)
    async def fuju_button_callback(
        self, interaction: discord.Interaction, button: Button
    ):
        uid = interaction.user.id
        member = interaction.guild.get_member(uid)
        role = discord.utils.get(interaction.guild.roles, name="ふじゅ〜")
        if role in member.roles:
            await member.remove_roles(role)
            await interaction.response.send_message(
                "ふじゅ〜の利用者登録が完了しました！", ephemeral=True
            )
        else:
            await member.add_roles(role)
            await interaction.response.send_message(
                "ふじゅ〜の利用者登録を解除しました！", ephemeral=True
            )


class Fuju(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_connection(self) -> aiomysql.Connection:
        if self.bot.db is None:
            raise RuntimeError("DB pool is not initialized")
        return await self.bot.db.acquire()

    @commands.command()
    async def fuju(self, ctx):
        embed = discord.Embed(
            title="ふじゅ〜の利用者登録パネル",
            description="以下のボタンを押すとふじゅ〜の利用者登録が行われます。\n再度押すと登録が解除されるのでご注意ください。\n",
        )

        view = ButtonList(self.bot)
        await ctx.send(embed=embed, view=view)

    @app_commands.command(name="chackFuju", description="ふじゅ〜を確認する")
    @app_commands.describe(user="確認対象ユーザー")
    async def check_Fuju(
        self, interaction: discord.Interaction, user: discord.Member | None = None
    ) -> None:
        target = interaction.user or user
        inte_ch = interaction.channel.id
        ch = self.bot.get_channel(inte_ch)
        conn = await self._get_connection()
        try:
            async with conn.cursor() as cur:
                await cur.excute(
                    "SELECT points FROM user_points WHERE user_id = %s", (target.id)
                )
                row = await cur.fetchone()

            if row is None:
                await ch.send(f"{target.mention} のポイントは 0 です。")
            else:
                points = row[0]
                await ch.send(f"{target.mention} のポイントは {points} です。")
        finally:
            # aiomysql は release でプールに返す
            self.bot.db.release(conn)


async def setup(bot: commands.Bot):
    await bot.add_cog(Fuju(bot))
    print("Security cog loaded successfully.")
    print("Bot is ready to handle securities.")
