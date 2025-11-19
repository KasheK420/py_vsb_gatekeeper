"""
bot/cogs/verification.py
Main verification cog

Monitors verification channel for new users.
Provides button interactions for starting verification.
"""

import logging

import discord
from discord.ext import commands

from ..services.cas_service import CASService
from ..services.verification_service import VerificationService
from ..util.config_loader import Config

logger = logging.getLogger(__name__)


class VerificationCog(commands.Cog):
    """Handle user verification"""
    
    def __init__(self, bot, config: Config, cas_service: CASService, verification_service: VerificationService):
        self.bot = bot
        self.config = config
        self.cas_service = cas_service
        self.verification_service = verification_service
    
    async def send_verification_message(self, channel: discord.TextChannel):
        """Post verification message with SSO button"""
        
        # Clean old messages
        try:
            async for msg in channel.history(limit=50):
                if msg.author == self.bot.user:
                    try:
                        await msg.delete()
                    except discord.Forbidden:
                        logger.warning(f"Missing permission to delete message {msg.id}")
                    except discord.HTTPException as e:
                        logger.debug(f"Failed to delete message {msg.id}: {e}")
        except discord.Forbidden:
            logger.warning(f"Missing permission to read channel history in {channel.id}")
        except discord.HTTPException as e:
            logger.error(f"Failed to fetch channel history: {e}")
        
        # Create embed
        embed = discord.Embed(
            title="🔒 Verifikace",
            description=(
                "**Vítejte na studentském komunitním Discordu VŠB - TUO.**\n\n"
                "**Jak se verifikovat?**\n"
                "Pro vstup na celý Discord je potřeba zmáčknout tlačítko pod touto zprávou, "
                "pomocí kterého se vygeneruje unikátní odkaz na **SSO verifikaci**.\n\n"
                "Tento odkaz tě následně přesměruje na **oficiální přihlášení od VŠB - TUO** "
                f"({self.config.cas_server_url}).\n\n"
                "—\n"
                "**Welcome!** Click the button below to generate a unique **SSO verification** link. "
                f"You will be redirected to the official **VŠB - TUO login** page ({self.config.cas_server_url})."
            ),
            color=discord.Color.from_rgb(139, 195, 74)  # Pistachio green
        )
        embed.set_footer(text="VSB Discord Server • Secure authentication via VSB SSO")
        
        # Create button
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                label="Ověřit se / Verify",
                style=discord.ButtonStyle.primary,
                custom_id="auth_sso",
                emoji="🔒"
            )
        )
        
        await channel.send(embed=embed, view=view)
        logger.info(f"Verification message posted in channel {channel.id}")
    
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle button interactions"""
        if interaction.type != discord.InteractionType.component:
            return
        
        if interaction.data.get("custom_id") != "auth_sso":
            return
        
        await self.handle_verification_button(interaction)
    
    async def handle_verification_button(self, interaction: discord.Interaction):
        """Handle SSO authentication button click"""
        user_id = interaction.user.id
        username = interaction.user.name
        
        # Check if already verified
        if await self.verification_service.is_verified(user_id):
            await interaction.response.send_message(
                "✅ Již jsi ověřený! / You are already verified!",
                ephemeral=True
            )
            return
        
        # Check if re-verification is required
        requires, reason = await self.verification_service.requires_reverification(user_id)
        
        if requires:
            await interaction.response.send_message(
                f"🔐 Vyžaduje se opětovné ověření / Re-verification required: {reason}\n\n"
                f"Zkontroluj své DM pro odkaz na ověření / Check your DMs for the verification link.",
                ephemeral=True
            )
            # Send re-verification link
            auth_url, _ = await self.cas_service.generate_verification_url(
                user_id,
                interaction.guild_id,
                is_reverification=True
            )
            await self._send_verification_dm(interaction.user, auth_url, is_reverification=True)
            return
        
        # Generate verification URL
        auth_url, _ = await self.cas_service.generate_verification_url(
            user_id,
            interaction.guild_id,
            is_reverification=False
        )
        
        # Create link button
        view = discord.ui.View()
        link_button = discord.ui.Button(
            label="Otevřít VSB SSO / Open VSB SSO",
            style=discord.ButtonStyle.link,
            url=auth_url,
            emoji="🔐"
        )
        view.add_item(link_button)
        
        await interaction.response.send_message(
            "Klikni na tlačítko pro otevření VSB SSO přihlášení:\n"
            "Click the button to open VSB SSO login:",
            view=view,
            ephemeral=True
        )
        
        logger.info(f"Verification started for user {user_id} ({username})")
    
    async def _send_verification_dm(self, user: discord.User, auth_url: str, is_reverification: bool = False):
        """Send verification DM with CAS link"""
        
        if is_reverification:
            title = "🔐 Opětovné ověření vyžadováno / Re-verification Required"
            description = (
                f"Ahoj {user.mention}!\n\n"
                f"Vyžaduje se opětovné ověření tvého účtu pomocí VSB SSO.\n\n"
                f"Hello {user.mention}!\n\n"
                f"Re-verification of your account via VSB SSO is required.\n\n"
                f"Klikni na odkaz níže pro ověření / Click the link below to verify:"
            )
        else:
            title = "🎓 Ověření Univerzity / University Verification"
            description = (
                f"Vítej na serveru, {user.mention}!\n\n"
                f"Pro přístup na server musíš ověřit svůj univerzitní účet "
                f"pomocí CAS (Central Authentication Service).\n\n"
                f"Welcome to the server, {user.mention}!\n\n"
                f"To access the server, you need to verify your university account "
                f"using CAS (Central Authentication Service).\n\n"
                f"**Tento proces:**\n"
                f"• Propojí tvůj Discord s univerzitním účtem\n"
                f"• Přiřadí odpovídající role (Student/Učitel)\n"
                f"• Trvá méně než 1 minutu\n\n"
                f"**This process:**\n"
                f"• Links your Discord to your university account\n"
                f"• Assigns appropriate roles (Student/Teacher)\n"
                f"• Takes less than 1 minute"
            )
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.green() if not is_reverification else discord.Color.orange()
        )
        
        embed.add_field(
            name="🔗 Odkaz na ověření / Verification Link",
            value=f"[Ověřit pomocí CAS / Verify with CAS]({auth_url})",
            inline=False
        )
        
        embed.set_footer(text="Odkaz vyprší za 15 minut / Link expires in 15 minutes")
        
        try:
            await user.send(embed=embed)
            logger.debug(f"Sent verification DM to user {user.id}")
        except discord.Forbidden:
            logger.warning(f"Cannot send DM to user {user.id} - DMs disabled")
    
    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        """Monitor verification channel and clean up user messages"""
        
        if msg.author.bot:
            return
        
        if msg.channel.id != self.config.verification_channel_id:
            return
        
        # Delete user messages in verification channel
        try:
            await msg.delete()
        except discord.Forbidden:
            logger.warning(f"Missing permission to delete message in verification channel")
        except discord.HTTPException as e:
            logger.debug(f"Failed to delete user message: {e}")
        
        # Check if already verified
        if await self.verification_service.is_verified(msg.author.id):
            try:
                await msg.author.send("✅ Již jsi ověřený! / You are already verified!")
            except discord.Forbidden:
                logger.debug(f"Cannot send DM to user {msg.author.id} - DMs disabled")
            except discord.HTTPException as e:
                logger.debug(f"Failed to send DM to user {msg.author.id}: {e}")
            return


async def setup(bot):
    """Setup function for loading the cog"""
    config = bot.config
    cas_service = bot.cas_service
    verification_service = bot.verification_service
    
    cog = VerificationCog(bot, config, cas_service, verification_service)
    await bot.add_cog(cog)
    
    # Post verification message
    channel = bot.get_channel(config.verification_channel_id)
    if channel:
        await cog.send_verification_message(channel)