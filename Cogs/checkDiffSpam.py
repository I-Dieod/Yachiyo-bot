import re
from difflib import SequenceMatcher

import discord


class CheckDiffSpam:
    def __init__(self, bot):
        self.bot = bot
        self.log_ch = 1478490523592560681  # 超かぐや姫！ファンサーバー server-log
        self.normalRole = 1473305169310515425  # 雑談ロール
        self.muteRole = 1478580818954686524  # おいたはダメだよ～ロール

        self.detect_len = 200
        # サイリウム絵文字パターン（色名部分を柔軟に）
        self.CYALUME_EMOJI_PATTERN = r":cyalume_light\d+_[a-zA-Z]+:\d+"

        # チャンネルベースの監視システム
        self.monitoring_channels = set()  # 監視中のチャンネルID
        self.channel_message_buffer = {}  # {channel_id: [message1, message2, message3, message4, message5]}
        self.consecutive_low_similarity = {}  # {channel_id: count} 連続する類似度0.9未満のカウント

    async def give_mute(self, member: discord.Member):
        try:
            role_Normal = member.guild.get_role(self.normalRole)
            role_Mute = member.guild.get_role(self.muteRole)

            # ロールの存在確認
            if role_Mute is None:
                print(f"Error: Mute role (ID: {self.muteRole}) not found")
                return False

            if role_Normal is None:
                print(f"Warning: Normal role (ID: {self.normalRole}) not found")

            # ミュートロール付与
            await member.add_roles(role_Mute)

            # 一般ロール削除（存在する場合のみ）
            if role_Normal is not None:
                await member.remove_roles(role_Normal)

            return True

        except discord.Forbidden:
            print(f"Permission error: Cannot modify roles for {member}")
            return False
        except Exception as e:
            print(f"Error in give_mute: {e}")
            return False

    def normalize_text_for_similarity(self, text):
        """類似度計算用にテキストを正規化"""
        # cyalume_light系絵文字を除去
        normalized = re.sub(self.CYALUME_EMOJI_PATTERN, "", text)

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
        if channel_id not in self.consecutive_low_similarity:
            self.consecutive_low_similarity[channel_id] = 0

    async def stop_channel_monitoring(self, channel_id):
        """チャンネル監視を停止してバッファをリセット"""
        if channel_id in self.monitoring_channels:
            self.monitoring_channels.remove(channel_id)
        if channel_id in self.channel_message_buffer:
            del self.channel_message_buffer[channel_id]
        if channel_id in self.consecutive_low_similarity:
            del self.consecutive_low_similarity[channel_id]

    async def check_monitoring_stop_condition(self, channel_id):
        """監視停止条件をチェック"""
        # 連続して3つのメッセージが類似度0.9未満になったら監視停止
        if channel_id in self.consecutive_low_similarity:
            if self.consecutive_low_similarity[channel_id] >= 3:
                await self.stop_channel_monitoring(channel_id)
                # ログチャンネルに監視停止を報告
                log_channel = self.bot.get_channel(self.log_ch)
                if log_channel:
                    await log_channel.send(
                        f"📊 チャンネル監視停止: <#{channel_id}>\n"
                        f"理由: 連続する3つのメッセージが類似度0.9未満"
                    )

    async def check_diffspam_and_mute(self, message):
        """スパム検出とミュート処理（チャンネルベース）"""
        channel_id = message.channel.id
        content = message.content

        # ボットのメッセージは無視
        if message.author.bot:
            return

        # 200文字超えのメッセージが来たら監視開始
        if (
            len(content) > self.detect_len
            and channel_id not in self.monitoring_channels
        ):
            await self.start_channel_monitoring(channel_id)

        # 監視中のチャンネルでない場合は何もしない
        if channel_id not in self.monitoring_channels:
            return

        # バッファにメッセージを追加
        if channel_id not in self.channel_message_buffer:
            self.channel_message_buffer[channel_id] = []

        buffer = self.channel_message_buffer[channel_id]

        # 監視中は文字数に関わらず類似度をチェック
        max_similarity = 0.0
        spam_detected = False

        # 200文字超えの場合のみスパム判定を行う
        if len(content) > self.detect_len:
            # バッファ内の各メッセージと類似度を比較
            for old_message in buffer:
                similarity = self.calculate_similarity(content, old_message)
                max_similarity = max(max_similarity, similarity)

                # 9割以上の類似度を検出
                if similarity >= 0.9:
                    spam_detected = True
                    # give_mute関数を使用してミュートロール付与（権限競合回避）
                    mute_success = await self.give_mute(message.author)

                    if mute_success:
                        # ログチャンネルに報告
                        log_channel = self.bot.get_channel(self.log_ch)
                        if log_channel:
                            await log_channel.send(
                                f"🚨 スパム検出: <@{message.author.id}> にミュートロールを付与しました。\n"
                                f"類似度: {similarity:.2%}\n"
                                f"チャンネル: {message.channel.name} (ID: {message.channel.id})\n"
                                f"メッセージ長: {len(content)}文字"
                            )

                        # メッセージを削除
                        await message.delete()
                    else:
                        # ミュート失敗の場合のログ
                        log_channel = self.bot.get_channel(self.log_ch)
                        if log_channel:
                            await log_channel.send(
                                f"⚠️ スパム検出: <@{message.author.id}> のスパムを検出しましたが、ミュート処理に失敗しました。\n"
                                f"類似度: {similarity:.2%}\n"
                                f"チャンネル: {message.channel.name} (ID: {message.channel.id})"
                            )
                    return

        # 全てのメッセージ（文字数問わず）に対して類似度チェック（監視停止判定用）
        if len(buffer) > 0:
            # バッファ内の全メッセージとの最大類似度を計算
            for old_message in buffer:
                similarity = self.calculate_similarity(content, old_message)
                max_similarity = max(max_similarity, similarity)

        # 類似度による監視停止条件の更新
        if len(buffer) > 0:  # バッファに何かメッセージがある場合
            if max_similarity < 0.9:
                # 連続する低類似度カウントを増加
                if channel_id not in self.consecutive_low_similarity:
                    self.consecutive_low_similarity[channel_id] = 0
                self.consecutive_low_similarity[channel_id] += 1
            else:
                # 類似度が0.9以上の場合、連続カウントをリセット
                self.consecutive_low_similarity[channel_id] = 0

        # バッファに新しいメッセージを追加（全メッセージ対象）
        buffer.append(content)
        # 最新5つのメッセージのみ保持
        if len(buffer) > 5:
            buffer.pop(0)

        # 監視停止条件をチェック
        await self.check_monitoring_stop_condition(channel_id)
