import re

import discord
from checkDiffSpam import CheckDiffSpam
from discord.ext import commands

mute_name_list = ["荒らし共栄圏", "荒らし", "共栄圏", "ワッパステイ", "サウロン"]
pattern1 = r"[\w-]{20,28}\.[\w-]{3,10}\.[\w-]{22,30}"
pattern2 = r"mfa\.[\w-]{80,90}"
pattern3 = r"[a-zA-Z0-9]{15}"
log_ch = 1478490523592560681  # 超かぐや姫！ファンサーバー server-log
muteRole = 1478580818954686524


class Security(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cds = CheckDiffSpam(self.bot)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        name = member.global_name or member.display_name
        ch = self.bot.get_channel(log_ch)
        for target in mute_name_list:
            if target in name:
                role = member.guild.get_role(muteRole)  # おいたはダメだよ〜
                await member.add_roles(role)
                if ch:
                    await ch.send("コンディション更新、カラーオレンジです。")

    # 荒らし文字列削除アルゴリズム + スパム検出
    @commands.Cog.listener()
    async def on_message(self, ctx):
        # チャンネルベースのスパム検出とミュート処理を先に実行
        await self.cds.check_diffspam_and_mute(ctx)
        block_ss = ["硬貨", "やじゅ〜", "ヤチヨ", "FUSHI", "ツクヨ民"]

        msg = ctx.content
        msg_len = len(msg)
        cat = re.findall(r"[^|~*`]", msg)
        cat_msg = "".join(cat)

        # 全ての単語が msg に含まれている場合のみ True
        if all(word in msg for word in block_ss):
            await ctx.delete()

        if re.search(pattern1, cat_msg) or re.search(
            pattern2, cat_msg
        ):  # トークン文字列
            await ctx.delete()
            await ctx.channel.send("トークンの恐れがある文字列を削除しました。")
            m_author = ctx.author.id
            msg_c_id = ctx.channel.id
            msg_c_name = ctx.channel.name

            ch = self.bot.get_channel(log_ch)
            await ch.send(f"<@{m_author}> がトークンメッセージを送信しました。\n")
            await ch.send(f"発生場所:{msg_c_name}(id: {msg_c_id})")

        if re.search(pattern3, msg) and msg_len == 15:  # スパム回避
            await ctx.delete()

    # 時間経過 メッセージ編集トークン化対策
    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        channel = self.bot.get_channel(payload.channel_id)
        if channel is None:
            return

        try:
            # 実際の Message オブジェクトを取りに行く
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return

        msg_after = message.content
        if re.search(pattern1, msg_after) or re.search(pattern2, msg_after):
            m_author = message.author.id
            msg_c_id = message.channel.id
            msg_c_name = message.channel.name

            ch = self.bot.get_channel(log_ch)
            await message.delete()
            if ch:
                await ch.send(f"<@{m_author}> がメッセージを編集しトークン化しました。")
                await ch.send(f"発生場所:{msg_c_name}(id: {msg_c_id})")

    @commands.command()
    async def Stest(self, ctx):
        name = ctx.author.global_name or ctx.author.display_name

        ch = self.bot.get_channel(1474755956171604118)  # Lunar-Project log
        if ch:
            for target in mute_name_list:
                if target in name:
                    await ch.send("危険な名前")


async def setup(bot: commands.Bot):
    await bot.add_cog(Security(bot))
    print("Security cog loaded successfully.")
    print("Bot is ready to handle securities.")
