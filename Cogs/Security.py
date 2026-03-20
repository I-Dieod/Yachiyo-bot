import logging
import re
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from data.client import db_manager

from .checkDiffSpam import CheckDiffSpam

logger = logging.getLogger(__name__)

mute_name_list = ["荒らし共栄圏", "荒らし", "共栄圏", "ワッパステイ", "サウロン"]
pattern1 = r"[\w-]{20,28}\.[\w-]{3,10}\.[\w-]{22,30}"
pattern2 = r"mfa\.[\w-]{80,90}"
pattern3 = r"[a-zA-Z0-9]{15}"

LOG_CH = 1484528280173547582  # 超かぐや姫！ファンサーバー yachiyo-log
NORMAL_ROLE = 1473305169310515425  # 雑談ロール
MUTE_ROLE = 1478580818954686524  # おいたはダメだよ～ロール


class Security(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cds = CheckDiffSpam(self.bot)

    async def cog_load(self):
        """Cogが読み込まれた時にデータベースを初期化"""
        try:
            if not db_manager.pool:
                await db_manager.create_pool()
                await db_manager.initialize_tables()
                logger.info("Database initialized for Security cog")
        except Exception as e:
            logger.error(f"Failed to initialize database for Security cog: {e}")

        self.expire_users_after1D.start()
        logger.info("expire_users_after1D task started")

    async def cog_unload(self):
        """Cogがアンロードされる時にデータベース接続を閉じる"""
        self.expire_users_after1D.cancel()
        logger.info("expire_users_after1D task cancelled")

        try:
            await db_manager.close_pool()
            logger.info("Database connection closed for Security cog")
        except Exception as e:
            logger.error(f"Failed to close database connection: {e}")

    async def give_mute(self, member: discord.Member):
        role_Normal = member.guild.get_roles(NORMAL_ROLE)
        role_Mute = member.guild.get_role(MUTE_ROLE)  # おいたはダメだよ〜
        await member.add_roles(role_Mute)
        await member.remove_roles(role_Normal)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # ユーザーIDと参加時間をデータベースに保存
        join_time = datetime.now()

        try:
            await db_manager.save_user_join(
                user_id=member.id,
                join_time=join_time,
                username=member.name,
                display_name=member.display_name,
                global_name=member.global_name,
            )
            logger.info(f"User join saved to database: {member.id}")
        except Exception as e:
            logger.error(f"Failed to save user join to database: {e}")

        name = member.global_name or member.display_name
        ch = self.bot.get_channel(LOG_CH)

        # 危険ユーザーミュート処理
        for target in mute_name_list:
            if target in name:
                role = member.guild.get_role(MUTE_ROLE)  # おいたはダメだよ〜
                await member.add_roles(role)
                if ch:
                    await ch.send(
                        ":orange_circle:コンディション更新、カラーオレンジです。"
                    )

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

            ch = self.bot.get_channel(LOG_CH)
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

    @app_commands.command(name="mute", description="直近24時間の参加者をミュートする")
    async def slash_mute(self, interaction: discord.Interaction) -> None:
        pass

    @commands.command()
    async def join_info(self, ctx, user_id: int = None):
        """ユーザーの参加情報を表示"""
        if user_id is None:
            user_id = ctx.author.id

        try:
            join_info = await db_manager.get_user_join_info(user_id)
            if join_info:
                join_time = join_info["join_time"]
                formatted_time = join_time.strftime("%Y年%m月%d日 %H:%M:%S")

                embed = discord.Embed(title="参加情報", color=0x00FF00)
                embed.add_field(name="ユーザー", value=f"<@{user_id}>", inline=False)
                embed.add_field(name="参加時刻", value=formatted_time, inline=False)

                if join_info.get("display_name"):
                    embed.add_field(
                        name="表示名", value=join_info["display_name"], inline=True
                    )
                if join_info.get("global_name"):
                    embed.add_field(
                        name="グローバル名", value=join_info["global_name"], inline=True
                    )

                await ctx.send(embed=embed)
            else:
                await ctx.send(
                    f"ユーザー <@{user_id}> の参加情報が見つかりませんでした。"
                )
        except Exception as e:
            logger.error(f"Failed to get user join info: {e}")
            await ctx.send("参加情報の取得中にエラーが発生しました。")

    @commands.command()
    async def join_stats(self, ctx):
        """サーバーの参加統計を表示"""
        try:
            total_count = await db_manager.get_user_join_count()

            embed = discord.Embed(title="参加統計", color=0x0099FF)
            embed.add_field(name="総参加記録数", value=f"{total_count}件", inline=False)
            embed.add_field(
                name="現在のメンバー数",
                value=f"{ctx.guild.member_count}人",
                inline=False,
            )

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Failed to get join stats: {e}")
            await ctx.send("統計情報の取得中にエラーが発生しました。")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def cleanup_joins(self, ctx, days: int = 90):
        """古い参加記録をクリーンアップ（管理者のみ）"""
        if days < 1:
            await ctx.send("日数は1以上である必要があります。")
            return

        try:
            deleted_count = await db_manager.cleanup_old_records(days)
            await ctx.send(f"{days}日より古い参加記録を{deleted_count}件削除しました。")
        except Exception as e:
            logger.error(f"Failed to cleanup old records: {e}")
            await ctx.send("クリーンアップ中にエラーが発生しました。")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def delete_user_joins(self, ctx, user_id: int):
        """特定ユーザーの参加記録を削除（管理者のみ）"""
        try:
            deleted_count = await db_manager.delete_user_join_records(user_id)
            await ctx.send(
                f"ユーザー <@{user_id}> の参加記録を{deleted_count}件削除しました。"
            )
        except Exception as e:
            logger.error(f"Failed to delete user join records: {e}")
            await ctx.send("記録削除中にエラーが発生しました。")

    @tasks.loop(hours=1)
    async def expire_users_after1D(self):
        """1時間ごとにDBをチェックし、join_timeが1日を超えたレコードを削除する"""
        try:
            deleted_count = await db_manager.delete_expired_joins()
            if deleted_count > 0:
                logger.info(
                    f"expire_users_after1D: {deleted_count}件の期限切れレコードを削除しました"
                )
            else:
                logger.debug(
                    "expire_users_after1D: 削除対象のレコードはありませんでした"
                )
        except Exception as e:
            logger.error(
                f"expire_users_after1D: レコード削除中にエラーが発生しました: {e}"
            )

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def db_test(self, ctx):
        """データベース接続をテスト（管理者のみ）"""
        try:
            # Test basic connection
            if not db_manager.pool:
                await ctx.send("❌ データベース接続プールが初期化されていません。")
                return

            async with db_manager.pool.acquire() as connection:
                # Test PostgreSQL version
                version = await connection.fetchval("SELECT version()")

                # Test table exists
                table_exists = await connection.fetchval(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_joins')"
                )

                # Test record count
                record_count = await connection.fetchval(
                    "SELECT COUNT(*) FROM user_joins"
                )

                embed = discord.Embed(title="データベース接続テスト", color=0x00FF00)
                embed.add_field(name="接続状態", value="✅ 正常", inline=False)
                embed.add_field(
                    name="PostgreSQL バージョン",
                    value=version.split()[1] if version else "不明",
                    inline=False,
                )
                embed.add_field(
                    name="user_joins テーブル",
                    value="✅ 存在" if table_exists else "❌ 存在しない",
                    inline=True,
                )
                embed.add_field(name="総記録数", value=f"{record_count}件", inline=True)

                await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Database test failed: {e}")
            embed = discord.Embed(title="データベース接続テスト", color=0xFF0000)
            embed.add_field(name="接続状態", value="❌ エラー", inline=False)
            embed.add_field(name="エラー内容", value=str(e)[:1000], inline=False)
            await ctx.send(embed=embed)

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
