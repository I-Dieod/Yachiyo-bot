from datetime import datetime
from typing import Optional, Union

import discord
from discord.ext import commands
from discord.ui import Button, Modal, TextInput, View

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
    applicant: discord.Member,
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

    def __init__(self, applicant: discord.Member, reason: str, period: str):
        super().__init__(timeout=None)
        self.applicant = applicant
        self.reason = reason
        self.period = period

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

        try:
            await self.applicant.add_roles(role)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ ロール付与の権限がありません。", ephemeral=True
            )
            return

        # 申請者にDMで通知
        try:
            await self.applicant.send(
                embed=discord.Embed(
                    title="✅ ロール申請が許可されました",
                    description=(
                        f"**{role.name}** のロール申請が承認されました！\n\n"
                        f"📝 申請理由: {self.reason}\n"
                        f"📅 申請日: {self.period}"
                    ),
                    color=discord.Color.green(),
                )
            )
        except discord.Forbidden:
            pass  # DMが送れない場合はスキップ

        approved_embed = _build_reviewed_embed(
            applicant=self.applicant,
            reason=self.reason,
            period=self.period,
            reviewer=interaction.user,
            approved=True,
        )
        await interaction.response.edit_message(embed=approved_embed, view=None)

    @discord.ui.button(
        label="❌ 却下", style=discord.ButtonStyle.danger, custom_id="review_reject"
    )
    async def reject(self, interaction: discord.Interaction, button: Button):
        """ロール付与を却下する"""

        # 申請者にDMで通知
        try:
            await self.applicant.send(
                embed=discord.Embed(
                    title="❌ ロール申請が却下されました",
                    description=(
                        "ステージコーディネーターのロール申請は却下されました。\n\n"
                        f"📝 申請理由: {self.reason}\n"
                        f"📅 申請日: {self.period}\n\n"
                        "詳細については管理者にお問い合わせください。"
                    ),
                    color=discord.Color.red(),
                )
            )
        except discord.Forbidden:
            pass  # DMが送れない場合はスキップ

        rejected_embed = _build_reviewed_embed(
            applicant=self.applicant,
            reason=self.reason,
            period=self.period,
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
        if applied_date <= today:
            await interaction.response.send_message(
                "❌ 申請日は本日より後の日付を入力してください。",
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
        view = ReviewView(
            applicant=member,
            reason=self.reason.value,
            period=normalized_period,
        )
        await review_channel.send(embed=embed, view=view)

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

    @commands.command()
    async def role(self, ctx: commands.Context):
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
    await bot.add_cog(StageEvent(bot))
    print("StageEvent cog loaded successfully.")
