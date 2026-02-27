import asyncio
import logging
import os

import discord
from aiohttp import web
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# Set the logging level for discord.py to DEBUG
logging.basicConfig(level=logging.DEBUG)
# token
token = os.getenv("BOT_TOKEN")

INITIAL_EXTENSIONS = [
    "Cogs.Events",
    "Cogs.Talk",
]


class Yachiyo(commands.Bot):
    def __init__(self, command_prefix, intents, help_command, strip_after_prefix):
        super().__init__(
            command_prefix=command_prefix,
            intents=intents,
            help_command=help_command,
            strip_after_prefix=strip_after_prefix,
        )
        self.remove_command("help")
        self.db = None

    async def setup_hook(self) -> None:

        # Cogs load Section
        for cog in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(cog)
                logging.info(f"Successfully loaded extension {cog}")
                print(f"Successfully loaded extension {cog}")
            except Exception as e:
                logging.error(f"Failed to load extension {cog}: {e}")
                print(f"Failed to load extension {cog}: {e}")

        # Sync slash commands
        try:
            synced = await self.tree.sync()
            logging.info(f"Synced {len(synced)} command(s)")
            print(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            logging.error(f"Failed to sync commands: {e}")
            print(f"Failed to sync commands: {e}")

        logging.info("Yachiyo is All Ready")


async def health_check_handler(request):
    """Health check endpoint for Railway"""
    return web.Response(text="OK", status=200)


async def start_health_server():
    """Start a simple HTTP server for health checks"""
    app = web.Application()
    app.router.add_get("/", health_check_handler)
    app.router.add_get("/health", health_check_handler)

    port = int(os.getenv("PORT", 8000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Health check server started on port {port}")


async def main():
    """Main function to run both Discord bot and health check server"""
    intents = discord.Intents.all()
    bot = Yachiyo(
        command_prefix="y!", intents=intents, help_command=None, strip_after_prefix=True
    )

    # Start health check server
    await start_health_server()

    # Start Discord bot
    await bot.start(token)


if __name__ == "__main__":
    # Validate token
    if not token:
        print("ERROR: BOT_TOKEN environment variable is not set!")
        print("Please set the BOT_TOKEN environment variable in Railway dashboard")
        exit(1)

    print(f"Token loaded: {'*' * (len(token) - 6) + token[-6:] if token else 'None'}")

    try:
        asyncio.run(main())
    except discord.LoginFailure:
        print("ERROR: Invalid bot token provided!")
        print("Please check your BOT_TOKEN environment variable")
    except Exception as e:
        print(f"ERROR: An unexpected error occurred: {e}")
