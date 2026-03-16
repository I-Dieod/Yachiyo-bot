import re
from difflib import SequenceMatcher

import discord
from discord.ext import commands

mute_name_list = ["荒らし共栄圏", "荒らし", "共栄圏", "ワッパステイ", "サウロン"]
pattern1 = r"[\w-]{20,28}\.[\w-]{3,10}\.[\w-]{22,30}"
pattern2 = r"mfa\.[\w-]{80,90}"
pattern3 = r"[a-zA-Z0-9]{15}"
log_ch = 1478490523592560681  # 超かぐや姫！ファンサーバー server-log
muteRole = 1478580818954686524
detect_len = 5000

# カスタム絵文字のパターン（cyalume_light系を特定）
CYALUME_EMOJI_PATTERN = r"<:cyalume_light\d*_[^:]*:\d+>"


class Security(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # チャンネルベースの監視システム
        self.monitoring_channels = set()  # 監視中のチャンネルID
        self.channel_message_buffer = {}  # {channel_id: [message1, message2, message3]}
        self.low_similarity_count = {}  # {channel_id: count} 類似度0.9未満のカウント

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

    def normalize_text_for_similarity(self, text):
        """類似度計算用にテキストを正規化"""
        # cyalume_light系絵文字を除去
        normalized = re.sub(CYALUME_EMOJI_PATTERN, "", text)

        # 連続する空白を単一の空白に統一
        normalized = re.sub(r"\s+", " ", normalized)

        # 前後の空白を除去
        return normalized.strip()

    def calculate_similarity(self, text1, text2):
        """2つのテキストの類似度を計算（0.0-1.0）- 絵文字を正規化して比較"""
        # 両方のテキストを正規化
        normalized_text1 = self.normalize_text_for_similarity(text1)
        normalized_text2 = self.normalize_text_for_similarity(text2)

        return SequenceMatcher(None, normalized_text1, normalized_text2).ratio()

    async def start_channel_monitoring(self, channel_id):
        """チャンネル監視を開始"""
        self.monitoring_channels.add(channel_id)
        if channel_id not in self.channel_message_buffer:
            self.channel_message_buffer[channel_id] = []
        if channel_id not in self.low_similarity_count:
            self.low_similarity_count[channel_id] = 0

    async def stop_channel_monitoring(self, channel_id):
        """チャンネル監視を停止してバッファをリセット"""
        if channel_id in self.monitoring_channels:
            self.monitoring_channels.remove(channel_id)
        if channel_id in self.channel_message_buffer:
            del self.channel_message_buffer[channel_id]
        if channel_id in self.low_similarity_count:
            del self.low_similarity_count[channel_id]

    async def check_monitoring_stop_condition(self, channel_id):
        """監視停止条件をチェック"""
        # 類似度が0.9を切ったカウントがバッファ中で2になったら監視停止
        if channel_id in self.low_similarity_count:
            if self.low_similarity_count[channel_id] >= 2:
                await self.stop_channel_monitoring(channel_id)
                # ログチャンネルに監視停止を報告
                log_channel = self.bot.get_channel(log_ch)
                if log_channel:
                    await log_channel.send(
                        f"📊 チャンネル監視停止: <#{channel_id}>\n"
                        f"理由: 類似度0.9未満のメッセージが2つに到達"
                    )

    async def check_diffspam_and_mute(self, message):
        """スパム検出とミュート処理（チャンネルベース）"""
        channel_id = message.channel.id
        content = message.content

        # ボットのメッセージは無視
        if message.author.bot:
            return

        # 200文字超えのメッセージが来たら監視開始
        if len(content) > detect_len and channel_id not in self.monitoring_channels:
            await self.start_channel_monitoring(channel_id)

        # 監視中のチャンネルでない場合は何もしない
        if channel_id not in self.monitoring_channels:
            return

        # バッファにメッセージを追加
        if channel_id not in self.channel_message_buffer:
            self.channel_message_buffer[channel_id] = []

        buffer = self.channel_message_buffer[channel_id]

        # 200文字超えのメッセージの場合、類似度をチェック
        if len(content) > detect_len:
            max_similarity = 0.0
            spam_detected = False

            # バッファ内の各メッセージと類似度を比較
            for old_message in buffer:
                similarity = self.calculate_similarity(content, old_message)
                max_similarity = max(max_similarity, similarity)

                # 9割以上の類似度を検出
                if similarity >= 0.9:
                    spam_detected = True
                    try:
                        # muteRoleを付与
                        role = message.guild.get_role(muteRole)
                        if role:
                            await message.author.add_roles(role)

                            # ログチャンネルに報告
                            log_channel = self.bot.get_channel(log_ch)
                            if log_channel:
                                await log_channel.send(
                                    f"🚨 スパム検出: <@{message.author.id}> にミュートロールを付与しました。\n"
                                    f"類似度: {similarity:.2%}\n"
                                    f"チャンネル: {message.channel.name} (ID: {message.channel.id})\n"
                                    f"メッセージ長: {len(content)}文字"
                                )

                            # メッセージを削除
                            await message.delete()
                            return

                    except discord.Forbidden:
                        # 権限不足の場合のログ
                        log_channel = self.bot.get_channel(log_ch)
                        if log_channel:
                            await log_channel.send(
                                f"⚠️ 権限不足: <@{message.author.id}> のスパムを検出しましたが、ミュートできませんでした。"
                            )
                    except Exception as e:
                        print(f"Error in spam detection: {e}")
                    break  # スパム検出したらループ終了

            # スパムが検出されなかった場合、最大類似度をチェック
            if not spam_detected and len(buffer) > 0:
                if max_similarity < 0.9:
                    # 類似度0.9未満のカウントを増加
                    if channel_id not in self.low_similarity_count:
                        self.low_similarity_count[channel_id] = 0
                    self.low_similarity_count[channel_id] += 1

        # バッファに新しいメッセージを追加（200文字超えのもののみ）
        if len(content) > detect_len:
            buffer.append(content)
            # 最新3つのメッセージのみ保持
            if len(buffer) > 3:
                buffer.pop(0)

        # 監視停止条件をチェック
        await self.check_monitoring_stop_condition(channel_id)

    # 荒らし文字列削除アルゴリズム + スパム検出
    @commands.Cog.listener()
    async def on_message(self, ctx):
        # チャンネルベースのスパム検出とミュート処理を先に実行
        await self.check_diffspam_and_mute(ctx)
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
