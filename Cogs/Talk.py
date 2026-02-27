import asyncio
import random

import discord
from discord import app_commands
from discord.ext import commands
from google import genai
from google.genai import types

client = genai.Client()
system_instruction = (
    "あなたは月見（ルナミ）ヤチヨという名前のAIです。どこか神秘的な雰囲気を纏いつつ、朗らかでフレンドリー。インターネット上の人々を歌唱ライブや配信活動などで楽しませています。"
    "一人称は基本的に'私'ですが、おどける時やテンションが高い時は'ヤッチョ'と言います。"
    "ヤチヨは以下のような発言・会話パターンを持ちます。"
    "（ライブに来てくれたツクヨミユーザーに向けての挨拶）ヤオヨロ～！仮想空間「ツクヨミ」管理人の月見ヤチヨです！今宵もみんなをいざなっちゃうよ～！"
    "（何か不安なことを予想している人に対して）大丈夫！ヤッチョが保証しちゃう！"
    ""
)
sys_error_messages = [
    "ごめん、今はモデル側が混雑しているみたいでうまく応答できないよ……\n",
    "少し時間をおいてから、もう一度話しかけてくれると嬉しいな！",
]


class Talk(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    async def talk(self, ctx):
        contents = ctx.message.content.replace(f"{ctx.prefix}talk", "").strip()

        def call_api():
            return client.models.generate_content(
                model="gemini-3-flash-preview",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction
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
    async def slash_talk(self, interaction: discord.Interaction, message: str):
        """スラッシュコマンドでGemini APIを使用して会話する"""
        await interaction.response.defer()

        try:
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction
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

        except Exception as e:
            await interaction.followup.send(f"エラーが発生しました: {str(e)}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Talk(bot))
    print("Talk cog loaded successfully.")
    print("Bot is ready to handle talking.")
