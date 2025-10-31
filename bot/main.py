"""
bot/main.py
Gatekeeper Bot - Main Entry Point

Discord verification bot with CAS/SAML SSO authentication.
"""

import asyncio
import logging
import sys
from pathlib import Path

import discord
from discord.ext import commands

from .db.database import close_database, init_database
from .services.cas_service import CASService
from .services.verification_service import VerificationService
from .util.config_loader import load_config
from .web.app import OAuthWebServer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("gatekeeper.log")
    ]
)

logger = logging.getLogger(__name__)


class Gatekeeper(commands.Bot):
    """Main bot class"""
    
    def __init__(self):
        # Load configuration
        self.config = load_config()
        
        # Initialize bot with intents
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.guilds = True
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        
        # Initialize services
        self.cas_service = CASService(self.config)
        self.verification_service = VerificationService(self.config)
        self.web_server = None
    
    async def setup_hook(self):
        """Called when the bot is starting"""
        logger.info("Initializing Gatekeeper...")
        
        # Initialize database
        await init_database(self.config.database_url)
        logger.info("Database initialized")
        
        # Load cogs
        cogs = [
            "bot.cogs.verification",
            "bot.cogs.user_events",
            "bot.cogs.verification_admin"
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}", exc_info=True)
        
        # Start web server
        self.web_server = OAuthWebServer(
            bot=self,
            config=self.config,
            cas_service=self.cas_service,
            verification_service=self.verification_service
        )
        asyncio.create_task(self.web_server.start())
        logger.info("OAuth web server started")
    
    async def on_ready(self):
        """Called when the bot is ready"""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guilds")
        logger.info("Gatekeeper is ready!")
        
        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="VSB SSO verifications"
            )
        )
    
    async def on_command_error(self, ctx, error):
        """Handle command errors"""
        if isinstance(error, commands.CommandNotFound):
            return
        
        logger.error(f"Command error: {error}", exc_info=True)
    
    async def close(self):
        """Clean shutdown"""
        logger.info("Shutting down Gatekeeper...")
        
        if self.web_server:
            await self.web_server.stop()
        
        await close_database()
        await super().close()
        
        logger.info("Gatekeeper shutdown complete")


async def main():
    """Main entry point"""
    bot = Gatekeeper()
    
    try:
        async with bot:
            await bot.start(bot.config.discord_token)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        await bot.close()


def run():
    """Run the bot"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()