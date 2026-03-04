import asyncio
import random
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from google import genai
from google.genai import types

client = genai.Client()
ch_work1 = 1477312385046810807  # 作業部屋1聞き専


def load_system_prompt():
    """システムプロンプトをマークダウンファイルから読み込む"""
    try:
        # プロジェクトのルートディレクトリのパスを取得
        current_dir = Path(__file__).parent
        root_dir = current_dir.parent
        prompt_file = root_dir / "system_prompt.md"

        with open(prompt_file, "r", encoding="utf-8") as f:
            content = f.read()

        # マークダウンのヘッダーやフォーマットを除去してプレーンテキストに変換
        lines = content.split("\n")
        processed_lines = []

        for line in lines:
            # 空行をスキップ
            if line.strip() == "":
                continue
            # リスト項目の場合は先頭の-を除去
            if line.strip().startswith("- "):
                processed_lines.append(line.strip()[2:])
            else:
                processed_lines.append(line.strip())

        return " ".join(processed_lines)

    except FileNotFoundError:
        print("Warning: system_prompt.md not found, using fallback prompt")
        return "あなたは「月見ヤチヨ」というキャラクターです。朗らかでフレンドリーに会話してください。"
    except Exception as e:
        print(f"Error loading system prompt: {e}")
        return "あなたは「月見ヤチヨ」というキャラクターです。朗らかでフレンドリーに会話してください。"


system_instruction = load_system_prompt()
sys_error_messages = [
    "ごめん、今はモデル側が混雑しているみたいでうまく応答できないよ……\n",
    "少し時間をおいてから、もう一度話しかけてくれると嬉しいな！",
]
trc_msg = []


class Talk(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_buffer = []
        self.target_channel_id = ch_work1  # 監視対象チャンネルID
        self.next_message_count = self._get_random_message_count()
        self.current_message_count = 0
        self.system_instruction = load_system_prompt()  # 動的にロード

    @commands.command()
    async def reload_prompt(self, ctx: commands.Context) -> None:
        """システムプロンプトをリロードする"""
        try:
            self.system_instruction = load_system_prompt()
            await ctx.send("✅ システムプロンプトをリロードしました！")
        except Exception as e:
            await ctx.send(f"❌ システムプロンプトのリロードに失敗しました: {e}")

    @commands.command()
    async def talk(self, ctx: commands.Context) -> None:
        contents = ctx.message.content.replace(f"{ctx.prefix}talk", "").strip()

        def call_api():
            return client.models.generate_content(
                model="gemini-3-flash-preview",
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction
                ),
                contents=contents,
            )

        try:
            response = await asyncio.to_thread(call_api)
            await ctx.send(f"Response: {response.text}")

        except Exception as err:
            msg = random.choice(sys_error_messages)
            await ctx.send(msg)
            print(f"Gemini error in talk command: {err}")

    @app_commands.command(name="talk", description="ヤチヨと会話する")
    @app_commands.describe(message="ヤチヨに送るメッセージ")
    async def slash_talk(self, interaction: discord.Interaction, message: str) -> None:
        """スラッシュコマンドでGemini APIを使用して会話する"""
        await interaction.response.defer()

        try:
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction
                ),
                contents=message,
            )

            # レスポンスが長すぎる場合は分割
            if len(response.text) > 2000:
                # 2000文字以内に分割
                chunks = [
                    response.text[i : i + 2000]
                    for i in range(0, len(response.text), 2000)
                ]
                await interaction.followup.send(chunks[0])
                for chunk in chunks[1:]:
                    await interaction.followup.send(chunk)
            else:
                await interaction.followup.send(response.text)

        except Exception as err:
            msg = random.choice(sys_error_messages)
            await interaction.followup.send(msg)
            print(f"Gemini error in talk command: {err}")

    def _get_random_message_count(self):
        """3-8の範囲でランダムなメッセージ数を取得"""
        return random.randint(3, 8)

    @commands.Cog.listener()
    async def on_message(self, message):
        # 指定されたチャンネルでのみ動作
        if message.channel.id != self.target_channel_id:
            return

        # ボット自身のメッセージの場合
        if message.author.bot:
            # ボットのメッセージもバッファに追加（一貫性のため）
            if message.author.id == self.bot.user.id:
                self.message_buffer.append(
                    {
                        "author": "ヤチヨ",
                        "content": message.content,
                        "timestamp": message.created_at,
                        "is_bot": True,
                    }
                )
                # バッファサイズを制限（最新の20メッセージのみ保持）
                if len(self.message_buffer) > 20:
                    self.message_buffer.pop(0)
            return

        # ユーザーメッセージをバッファに追加
        self.message_buffer.append(
            {
                "author": message.author.display_name,
                "content": message.content,
                "timestamp": message.created_at,
                "is_bot": False,
            }
        )

        # バッファサイズを制限（最新の20メッセージのみ保持）
        if len(self.message_buffer) > 20:
            self.message_buffer.pop(0)

        self.current_message_count += 1

        # 目標メッセージ数に到達したら応答
        if self.current_message_count >= self.next_message_count:
            await self._send_ai_response(message.channel)
            self.current_message_count = 0
            self.next_message_count = self._get_random_message_count()

    async def _send_ai_response(self, channel):
        """AIの応答を生成してチャンネルに送信"""
        if not self.message_buffer:
            return

        # 最新のn個のメッセージを取得（最大10個）
        recent_messages = self.message_buffer[-min(len(self.message_buffer), 10) :]

        # プロンプトを構築（ボットの過去発言も含める）
        conversation_context = "最近の会話履歴:\n"
        for msg in recent_messages:
            conversation_context += f"{msg['author']}: {msg['content']}\n"

        conversation_context += "\n上記の会話履歴を踏まえて、過去の自分の発言と一貫性を保ちながら自然に会話に参加してください。矛盾する内容は避けてください。"

        def call_api():
            return client.models.generate_content(
                model="gemini-3-flash-preview",
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction
                ),
                contents=conversation_context,
            )

        try:
            response = await asyncio.to_thread(call_api)

            # レスポンスが長すぎる場合は分割
            if len(response.text) > 2000:
                chunks = [
                    response.text[i : i + 2000]
                    for i in range(0, len(response.text), 2000)
                ]
                sent_message = await channel.send(chunks[0])
                full_response = chunks[0]
                for chunk in chunks[1:]:
                    await channel.send(chunk)
                    full_response += chunk
            else:
                sent_msg = await channel.send(response.text)
                full_response = response.text
                trc_msg.append(sent_msg.id)

            # ボット自身のメッセージをバッファに追加（手動で追加、on_messageで重複処理を避けるため）
            # Note: on_messageリスナーで自動的に追加されるので、ここでの手動追加は不要

        except Exception as err:
            msg = random.choice(sys_error_messages)
            error_message = await channel.send(msg)
            print(f"Gemini error in auto response: {err}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Talk(bot))
    print("Talk cog loaded successfully.")
    print("Bot is ready to handle talking.")
