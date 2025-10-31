"""
bot/cogs/verification_admin.py
Admin commands for verification management

Commands:
- /reverify <user> - Manually require re-verification
- /verify-status <user> - Check verification status
- /setup-verification - Post verification message
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from ..db.database import get_session
from ..db.models import User, UserVerificationData
from ..services.cas_service import CASService
from ..services.verification_service import VerificationService
from ..util.config_loader import Config

logger = logging.getLogger(__name__)


def is_admin(user: discord.Member, config: Config) -> bool:
    """Check if user has admin or moderator role"""
    admin_roles = {config.admin_role_id, config.moderator_role_id}
    return any(role.id in admin_roles for role in user.roles if role.id)


class VerificationAdminCog(commands.Cog):
    """Admin verification management"""
    
    def __init__(self, bot, config: Config, cas_service: CASService, verification_service: VerificationService):
        self.bot = bot
        self.config = config
        self.cas_service = cas_service
        self.verification_service = verification_service
    
    @app_commands.command(name="reverify", description="Require user to re-verify (Admin)")
    @app_commands.describe(
        user="User to require re-verification",
        reason="Reason for re-verification"
    )
    async def reverify_user(
        self, 
        interaction: discord.Interaction, 
        user: discord.Member,
        reason: str = "Manual admin request"
    ):
        """Manually trigger re-verification for a user"""
        
        if not is_admin(interaction.user, self.config):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Preserve roles
        await self.verification_service.preserve_roles(user)
        
        # Mark for re-verification
        await self.verification_service.require_reverification(user.id, reason)
        
        # Remove roles (except @everyone and protected roles)
        protected_roles = {
            self.config.admin_role_id,
            self.config.moderator_role_id,
            self.config.host_role_id,
            self.config.absolvent_role_id
        }
        
        roles_to_remove = [
            r for r in user.roles 
            if r.id != interaction.guild.default_role.id and r.id not in protected_roles
        ]
        
        if roles_to_remove:
            await user.remove_roles(*roles_to_remove, reason=f"Re-verification required: {reason}")
        
        # Generate verification link
        auth_url, _ = await self.cas_service.generate_verification_url(
            user.id,
            interaction.guild_id,
            is_reverification=True
        )
        
        # Send DM to user
        embed = discord.Embed(
            title="🔐 Opětovné ověření vyžadováno / Re-verification Required",
            description=(
                f"Ahoj {user.mention},\n\n"
                f"Administrátor vyžaduje opětovné ověření tvého účtu.\n\n"
                f"Hello {user.mention},\n\n"
                f"An administrator has requested that you re-verify your account.\n\n"
                f"**Důvod / Reason:** {reason}\n\n"
                f"Tvé role byly dočasně pozastaveny a budou obnoveny po dokončení ověření.\n"
                f"Your roles have been temporarily suspended and will be restored once you complete re-verification."
            ),
            color=discord.Color.orange()
        )
        
        embed.add_field(
            name="🔗 Ověřit nyní / Re-verify Now",
            value=f"[Klikni zde pro ověření / Click here to re-verify]({auth_url})",
            inline=False
        )
        
        try:
            await user.send(embed=embed)
            dm_sent = True
        except discord.Forbidden:
            dm_sent = False
        
        # Confirm to admin
        await interaction.followup.send(
            f"✅ {user.mention} označen pro opětovné ověření / marked for re-verification.\n"
            f"Role uloženy a dočasně odebrány / Roles preserved and temporarily removed.\n"
            f"{'DM odeslána úspěšně / DM sent successfully.' if dm_sent else '⚠️ Nepodařilo se odeslat DM (uživatel má DM vypnuté) / Could not send DM (user has DMs disabled).'}",
            ephemeral=True
        )
        
        logger.info(f"Admin {interaction.user.id} triggered re-verification for user {user.id}: {reason}")
    
    @app_commands.command(name="verify-status", description="Check user verification status (Admin)")
    @app_commands.describe(user="User to check")
    async def verify_status(self, interaction: discord.Interaction, user: discord.Member):
        """Check verification status of a user"""
        
        if not is_admin(interaction.user, self.config):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        async with get_session() as session:
            # Get user data
            result = await session.execute(
                select(User).where(User.discord_id == user.id)
            )
            user_record = result.scalar_one_or_none()
            
            # Get verification data
            result = await session.execute(
                select(UserVerificationData).where(
                    UserVerificationData.discord_id == user.id
                )
            )
            ver_data = result.scalar_one_or_none()
            
            if not user_record or not ver_data:
                await interaction.followup.send(
                    f"❌ {user.mention} není ověřený / is not verified.",
                    ephemeral=True
                )
                return
            
            # Build status embed
            embed = discord.Embed(
                title=f"Stav ověření / Verification Status - {user.display_name}",
                color=discord.Color.green() if not ver_data.reverification_required else discord.Color.orange()
            )
            
            embed.set_thumbnail(url=user.display_avatar.url)
            
            embed.add_field(
                name="CAS Login",
                value=ver_data.cas_login,
                inline=True
            )
            embed.add_field(
                name="Real Name",
                value=ver_data.cas_real_name or "N/A",
                inline=True
            )
            embed.add_field(
                name="Email",
                value=ver_data.cas_email or "N/A",
                inline=True
            )
            
            embed.add_field(
                name="Typ / Type",
                value="Učitel / Teacher" if user_record.type == 2 else "Student",
                inline=True
            )
            embed.add_field(
                name="Aktivní / Active",
                value="✅ Ano / Yes" if user_record.activity == 1 else "❌ Ne / No",
                inline=True
            )
            embed.add_field(
                name="Ověřeno / Verified At",
                value=ver_data.verified_at.strftime("%Y-%m-%d %H:%M UTC") if ver_data.verified_at else "N/A",
                inline=True
            )
            
            embed.add_field(
                name="Poslední ověření / Last Re-verified",
                value=ver_data.last_reverified_at.strftime("%Y-%m-%d %H:%M UTC") if ver_data.last_reverified_at else "N/A",
                inline=True
            )
            
            if ver_data.reverification_required:
                embed.add_field(
                    name="⚠️ Vyžaduje opětovné ověření / Re-verification Required",
                    value=ver_data.reverification_reason or "Unknown reason",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        logger.debug(f"Admin {interaction.user.id} checked verification status for user {user.id}")
    
    @app_commands.command(name="setup-verification", description="Post verification message (Admin)")
    async def setup_verification(self, interaction: discord.Interaction):
        """Manually post verification message"""
        
        if not is_admin(interaction.user, self.config):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        channel = self.bot.get_channel(self.config.verification_channel_id)
        if not channel:
            await interaction.followup.send(
                "❌ Ověřovací kanál nenalezen / Verification channel not found.",
                ephemeral=True
            )
            return
        
        # Get verification cog and post message
        verification_cog = self.bot.get_cog("VerificationCog")
        if verification_cog:
            await verification_cog.send_verification_message(channel)
            await interaction.followup.send(
                f"✅ Ověřovací zpráva zveřejněna v / Verification message posted in {channel.mention}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ Ověřovací cog není načten / Verification cog not loaded.",
                ephemeral=True
            )
        
        logger.info(f"Admin {interaction.user.id} manually posted verification message")


async def setup(bot):
    """Setup function for loading the cog"""
    config = bot.config
    cas_service = bot.cas_service
    verification_service = bot.verification_service
    
    await bot.add_cog(VerificationAdminCog(bot, config, cas_service, verification_service))