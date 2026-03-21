import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Union

import discord
from discord.ext import commands, tasks
from discord.ui import Button, Modal, TextInput, View

from data.client import db_manager

JST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)

# 審査チャンネルのID
REVIEW_CHANNEL_ID = 1483869724482998383  # ステージコーディネート申請
APPLY_ROLE_ID = 1483867597777928362  # ステージコーディネーター


def _normalize_date(value: str) -> Optional[str]:
    """
    ユーザー入力の日付文字列を正規化して yyyy/mm/dd 形式で返す。
    区切り文字は / か - を許容。月・日はゼロ埋めなしでも受け付ける。
    不正な入力の場合は None を返す。
    """
    normalized = value.strip().replace("-", "/")

    parts = normalized.split("/")
    if len(parts) != 3:
        return None

    try:
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None

    # ゼロ埋めして strptime で存在チェック
    date_str = f"{year:04d}/{month:02d}/{day:02d}"
    try:
        datetime.strptime(date_str, "%Y/%m/%d")
    except ValueError:
        return None

    return date_str


# --- Embed生成ヘルパー ---
def _build_application_embed(
    applicant: discord.Member, reason: str, period: str
) -> discord.Embed:
    """審査チャンネルに送信する申請Embedを生成する"""
    embed = discord.Embed(
        title="📋 コーディネーターロールの新規申請",
        description=f"**{applicant.mention}** さんから新しいステージコーディネート申請が届きました。",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="👤 申請者", value=f"{applicant} (`{applicant.id}`)", inline=False
    )
    embed.add_field(name="📅 申請日", value=period, inline=True)
    embed.add_field(name="📝 申請理由", value=reason, inline=False)
    embed.set_thumbnail(url=applicant.display_avatar.url)
    embed.set_footer(text="下のボタンで申請を審査してください")
    return embed


def _build_reviewed_embed(
    applicant: Union[discord.Member, discord.User],
    reason: str,
    period: str,
    reviewer: Union[discord.Member, discord.User],
    approved: bool,
) -> discord.Embed:
    """審査完了後のEmbedを生成する"""
    status_label = "✅ 許可" if approved else "❌ 却下"
    color = discord.Color.green() if approved else discord.Color.red()

    embed = discord.Embed(
        title=f"📋 コーディネーターロール申請 — {status_label}",
        description=f"**{applicant.mention}** さんの申請は **{status_label}** されました。",
        color=color,
    )
    embed.add_field(
        name="👤 申請者", value=f"{applicant} (`{applicant.id}`)", inline=False
    )
    embed.add_field(name="📅 申請日", value=period, inline=True)
    embed.add_field(name="📝 申請理由", value=reason, inline=False)
    embed.add_field(
        name="🔎 審査者", value=f"{reviewer} (`{reviewer.id}`)", inline=False
    )
    embed.set_thumbnail(url=applicant.display_avatar.url)
    return embed


# --- 許可/却下ボタンのView ---
class ReviewView(View):
    """申請審査用のView（許可・却下ボタン）"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✅ 許可", style=discord.ButtonStyle.success, custom_id="review_approve"
    )
    async def approve(self, interaction: discord.Interaction, button: Button):
        """ロール付与を許可する"""
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ サーバー内でのみ使用できます。", ephemeral=True
            )
            return

        role = interaction.guild.get_role(APPLY_ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                "❌ 対象ロールが見つかりませんでした。", ephemeral=True
            )
            return

        # DBから申請情報を復元
        if interaction.message is None:
            await interaction.response.send_message(
                "❌ メッセージ情報が取得できませんでした。", ephemeral=True
            )
            return
        record = await db_manager.get_review_message(interaction.message.id)
        if record is None:
            await interaction.response.send_message(
                "❌ 申請情報が見つかりませんでした。", ephemeral=True
            )
            return

        applicant = interaction.guild.get_member(record["applicant_id"])
        if applicant is None:
            await interaction.response.send_message(
                "❌ 申請者がサーバーに見つかりませんでした。", ephemeral=True
            )
            return

        reason: str = record["reason"]
        period: date = record["period"]
        period_str = period.strftime("%Y/%m/%d")
        today_jst = interaction.created_at.astimezone(JST).date()

        try:
            await db_manager.save_applied_period(
                applicant.id,
                applicant.name,
                applicant.display_name,
                period,
            )
            # 申請日が当日（JST）であれば即時付与
            if period == today_jst:
                await applicant.add_roles(role)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ ロール付与の権限がありません。", ephemeral=True
            )
            return
        except Exception:
            await interaction.response.send_message(
                "❌ DB保存に失敗しました。", ephemeral=True
            )
            return

        # 審査メッセージレコードを削除
        await db_manager.delete_review_message(interaction.message.id)  # type: ignore[union-attr]

        # 申請者にDMで通知
        try:
            await applicant.send(
                embed=discord.Embed(
                    title="✅ ロール申請が許可されました",
                    description=(
                        f"**{role.name}** のロール申請が承認されました！\n\n"
                        f"📝 申請理由: {reason}\n"
                        f"📅 申請日: {period_str}"
                    ),
                    color=discord.Color.green(),
                )
            )
        except discord.Forbidden:
            pass  # DMが送れない場合はスキップ

        approved_embed = _build_reviewed_embed(
            applicant=applicant,
            reason=reason,
            period=period_str,
            reviewer=interaction.user,
            approved=True,
        )
        await interaction.response.edit_message(embed=approved_embed, view=None)

    @discord.ui.button(
        label="❌ 却下", style=discord.ButtonStyle.danger, custom_id="review_reject"
    )
    async def reject(self, interaction: discord.Interaction, button: Button):
        """ロール付与を却下する"""

        # DBから申請情報を復元
        if interaction.message is None:
            await interaction.response.send_message(
                "❌ メッセージ情報が取得できませんでした。", ephemeral=True
            )
            return
        record = await db_manager.get_review_message(interaction.message.id)
        if record is None:
            await interaction.response.send_message(
                "❌ 申請情報が見つかりませんでした。", ephemeral=True
            )
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ サーバー内でのみ使用できます。", ephemeral=True
            )
            return

        applicant = interaction.guild.get_member(record["applicant_id"])
        reason: str = record["reason"]
        period: date = record["period"]
        period_str = period.strftime("%Y/%m/%d")

        # 審査メッセージレコードを削除
        await db_manager.delete_review_message(interaction.message.id)  # type: ignore[union-attr]

        # 申請者にDMで通知
        try:
            if applicant is not None:
                await applicant.send(
                    embed=discord.Embed(
                        title="❌ ロール申請が却下されました",
                        description=(
                            "ステージコーディネーターのロール申請は却下されました。\n\n"
                            f"📝 申請理由: {reason}\n"
                            f"📅 申請日: {period_str}\n\n"
                            "詳細については管理者にお問い合わせください。"
                        ),
                        color=discord.Color.red(),
                    )
                )
        except discord.Forbidden:
            pass  # DMが送れない場合はスキップ

        # applicant が None の場合でも Embed は表示できるようダミーを用意
        dummy_applicant = applicant or interaction.user
        rejected_embed = _build_reviewed_embed(
            applicant=dummy_applicant,
            reason=reason,
            period=period_str,
            reviewer=interaction.user,
            approved=False,
        )
        await interaction.response.edit_message(embed=rejected_embed, view=None)


# --- モーダル定義 ---
class ApplicationModal(Modal, title="ステージコーディネーター申請"):
    reason = TextInput(
        label="申請理由",
        style=discord.TextStyle.paragraph,
        placeholder="申請理由を入力してください",
        required=True,
        max_length=300,
    )
    period = TextInput(
        label="申請日",
        style=discord.TextStyle.short,
        placeholder="例: 2025/4/1 または 2025-04-01",
        required=True,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ サーバー内でのみ使用できます。", ephemeral=True
            )
            return

        member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            await interaction.response.send_message(
                "❌ メンバー情報の取得に失敗しました。", ephemeral=True
            )
            return

        role = interaction.guild.get_role(APPLY_ROLE_ID)

        # 既にロールを所持している場合は除去フロー
        if role is not None and role in member.roles:
            await member.remove_roles(role)
            await interaction.response.send_message(
                "**ステージコーディネーター** のロールを除去しました。",
                ephemeral=True,
            )
            return

        # 日付の正規化・バリデーション
        normalized_period = _normalize_date(self.period.value)
        if normalized_period is None:
            await interaction.response.send_message(
                "❌ 申請日の形式が正しくありません。\n"
                "年/月/日 または 年-月-日 の形式で入力してください。\n"
                "例: `2025/4/1` `2025/04/01` `2025-4-1`",
                ephemeral=True,
            )
            return

        # 申請日がインタラクション日時より未来かチェック
        applied_date = datetime.strptime(normalized_period, "%Y/%m/%d")
        today = interaction.created_at.replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )
        if applied_date < today:
            await interaction.response.send_message(
                "❌ 申請日は本日以降の日付を入力してください。",
                ephemeral=True,
            )
            return

        # 審査チャンネルを取得し、テキスト系チャンネルに絞り込む
        raw_channel = interaction.guild.get_channel(REVIEW_CHANNEL_ID)
        if not isinstance(
            raw_channel,
            (discord.TextChannel, discord.Thread, discord.VoiceChannel),
        ):
            await interaction.response.send_message(
                "❌ 審査チャンネルが見つかりませんでした。管理者にお問い合わせください。",
                ephemeral=True,
            )
            return

        review_channel: Union[
            discord.TextChannel, discord.Thread, discord.VoiceChannel
        ] = raw_channel

        # 申請Embedを審査チャンネルに送信
        embed = _build_application_embed(
            applicant=member,
            reason=self.reason.value,
            period=normalized_period,
        )
        view = ReviewView()
        msg = await review_channel.send(embed=embed, view=view)

        # 審査メッセージをDBに保存
        await db_manager.save_review_message(
            msg.id,
            member.id,
            self.reason.value,
            datetime.strptime(normalized_period, "%Y/%m/%d").date(),
        )

        # 申請者に受付完了を通知（ephemeral）
        await interaction.response.send_message(
            "✅ **ステージコーディネーター** への申請を受け付けました！\n"
            "審査が完了次第、DMでお知らせします。",
            ephemeral=True,
        )


# --- 申請ボタンView ---
class ApplyView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="申請する",
        style=discord.ButtonStyle.primary,
        custom_id="apply_coordinator",
    )
    async def apply(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ApplicationModal())


# --- Cog ---
class StageEvent(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_role_schedule.start()

    async def cog_unload(self):
        self.check_role_schedule.cancel()

    @tasks.loop(hours=24)
    async def check_role_schedule(self):
        """
        毎日0時（JST）に実行:
        - applied_period が今日のレコード → ロールを付与
        - applied_period が今日より前のレコード → ロールを除去してDBから削除
        """
        today = datetime.now(JST).date()
        logger.info(f"[check_role_schedule] 発火: today(JST)={today}")

        if not self.bot.guilds:
            logger.warning("[check_role_schedule] bot.guilds が空のため終了")
            return
        guild = self.bot.guilds[0]

        try:
            # キャッシュが不完全な場合に備え fetch_guild でロール情報を確実に取得
            fetched_guild = await self.bot.fetch_guild(guild.id)
        except discord.HTTPException as e:
            logger.error(f"[check_role_schedule] fetch_guild 失敗: {e}")
            return

        role = fetched_guild.get_role(APPLY_ROLE_ID)
        if role is None:
            logger.warning(
                f"[check_role_schedule] APPLY_ROLE_ID={APPLY_ROLE_ID} のロールが見つからないため終了"
            )
            return

        # 当日分: ロールを付与（未付与の場合のみ）
        try:
            due_records = await db_manager.get_due_records(today)
            logger.info(f"[check_role_schedule] 当日対象レコード数: {len(due_records)}")
        except Exception as e:
            logger.error(f"[check_role_schedule] get_due_records 失敗: {e}")
            return

        for record in due_records:
            member = guild.get_member(record["user_id"])
            if member is None:
                logger.warning(
                    f"[check_role_schedule] user_id={record['user_id']} がギルドに見つからない（当日分）"
                )
                continue
            if role not in member.roles:
                try:
                    await member.add_roles(role)
                    logger.info(f"[check_role_schedule] ロール付与成功: {member}")
                except discord.Forbidden:
                    logger.error(f"[check_role_schedule] ロール付与権限なし: {member}")
            else:
                logger.info(
                    f"[check_role_schedule] 既にロール所持のためスキップ: {member}"
                )

        # 期限切れ分（< today）: ロールを除去してDBから削除
        try:
            expired_records = await db_manager.get_due_records_before(today)
            logger.info(
                f"[check_role_schedule] 期限切れ対象レコード数: {len(expired_records)}"
            )
        except Exception as e:
            logger.error(f"[check_role_schedule] get_due_records_before 失敗: {e}")
            return

        for record in expired_records:
            member = guild.get_member(record["user_id"])
            if member is not None and role in member.roles:
                try:
                    await member.remove_roles(role)
                    logger.info(f"[check_role_schedule] ロール除去成功: {member}")
                except discord.Forbidden:
                    logger.error(f"[check_role_schedule] ロール除去権限なし: {member}")
            else:
                logger.info(
                    f"[check_role_schedule] ロール除去スキップ: member={member}, user_id={record['user_id']}"
                )

        try:
            deleted = await db_manager.delete_expired_records(today)
            logger.info(f"[check_role_schedule] DB削除完了: {deleted} 件")
        except Exception as e:
            logger.error(f"[check_role_schedule] delete_expired_records 失敗: {e}")

    @check_role_schedule.before_loop
    async def before_check_role_schedule(self):
        """ボット起動完了を待ち、次の0時(JST)まで待機してからループを開始する"""
        await self.bot.wait_until_ready()

        now = datetime.now(JST)
        next_midnight = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        wait_seconds = (next_midnight - now).total_seconds()
        logger.info(
            f"[before_check_role_schedule] 次の0時(JST)まで {wait_seconds:.0f}秒 待機"
        )
        await asyncio.sleep(wait_seconds)

    @commands.command()
    async def stage_apply(self, ctx: commands.Context):
        embed = discord.Embed(
            title="ステージコーディネーター申請🎙️",
            description=(
                "ステージ利用を可能にする **ステージコーディネーター** ロールを申請できます。\n"
                "申請希望者は以下のボタンを押して、申請期間および申請理由を記入してください。\n"
            ),
        )
        view = ApplyView()
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    # 起動時に審査待ちの ReviewView を復元
    records = await db_manager.get_all_review_messages()
    for record in records:
        bot.add_view(ReviewView(), message_id=record["message_id"])
    logger.info(f"ReviewView restored for {len(records)} message(s)")

    # ApplyView も永続化
    bot.add_view(ApplyView())

    await bot.add_cog(StageEvent(bot))
    print("StageEvent cog loaded successfully.")
