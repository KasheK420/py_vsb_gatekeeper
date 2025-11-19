"""
bot/cogs/user_events.py
Handle Discord user events

Events:
- on_member_join - Create user record
- on_member_remove - Update status
- on_member_ban - Log ban
- on_member_unban - Log unban
"""

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands
from sqlalchemy import select

from ..db.database import get_session
from ..db.models import User, UserMetrics, UserStatusHistory
from ..util.config_loader import Config

logger = logging.getLogger(__name__)


class UserEventsCog(commands.Cog):
    """Track user join/leave/ban events"""
    
    def __init__(self, bot, config: Config):
        self.bot = bot
        self.config = config
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Create user record when someone joins"""
        
        if member.guild.id != self.config.guild_id:
            return
        
        async with get_session() as session:
            # Create or update user
            result = await session.execute(
                select(User).where(User.discord_id == member.id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                user = User(
                    discord_id=member.id,
                    login=f"discord_{member.id}",  # Temporary login until verified
                    activity=0,  # Inactive until verified
                    type=0,
                    is_bot=member.bot
                )
                session.add(user)
            
            # Create or update metrics
            result = await session.execute(
                select(UserMetrics).where(UserMetrics.discord_id == member.id)
            )
            metrics = result.scalar_one_or_none()
            
            if not metrics:
                metrics = UserMetrics(discord_id=member.id, join_count=1)
                session.add(metrics)
            else:
                metrics.join_count += 1
            
            # Log event
            history = UserStatusHistory(
                discord_id=member.id,
                guild_id=member.guild.id,
                event_type="join"
            )
            session.add(history)
            
            await session.commit()
        
        logger.info(f"User {member.id} ({member.name}) joined guild {member.guild.id}")
    
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Log when user leaves"""
        
        if member.guild.id != self.config.guild_id:
            return
        
        async with get_session() as session:
            # Get current roles
            role_ids = [r.id for r in member.roles if r.id != member.guild.default_role.id]
            
            # Log event
            history = UserStatusHistory(
                discord_id=member.id,
                guild_id=member.guild.id,
                event_type="leave",
                roles_at_event={"role_ids": role_ids}
            )
            session.add(history)
            
            await session.commit()
        
        logger.info(f"User {member.id} left guild {member.guild.id}")
    
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Log when user is banned"""
        
        if guild.id != self.config.guild_id:
            return
        
        async with get_session() as session:
            # Try to get ban entry for reason
            try:
                ban_entry = await guild.fetch_ban(user)
                reason = ban_entry.reason
            except discord.NotFound:
                reason = None
            except discord.Forbidden:
                logger.warning("Missing permission to fetch ban entry")
                reason = None
            except discord.HTTPException as e:
                logger.debug(f"Failed to fetch ban entry: {e}")
                reason = None
            
            # Log event
            history = UserStatusHistory(
                discord_id=user.id,
                guild_id=guild.id,
                event_type="ban",
                reason=reason
            )
            session.add(history)
            
            # Update metrics
            result = await session.execute(
                select(UserMetrics).where(UserMetrics.discord_id == user.id)
            )
            metrics = result.scalar_one_or_none()
            
            if metrics:
                metrics.bans += 1
            
            await session.commit()
        
        logger.warning(f"User {user.id} banned from guild {guild.id}: {reason}")
    
    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        """Log when user is unbanned"""
        
        if guild.id != self.config.guild_id:
            return
        
        async with get_session() as session:
            history = UserStatusHistory(
                discord_id=user.id,
                guild_id=guild.id,
                event_type="unban"
            )
            session.add(history)
            
            await session.commit()
        
        logger.info(f"User {user.id} unbanned from guild {guild.id}")


async def setup(bot):
    """Setup function for loading the cog"""
    config = bot.config
    await bot.add_cog(UserEventsCog(bot, config))