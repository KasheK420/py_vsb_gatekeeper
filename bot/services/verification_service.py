"""
bot/services/verification_service.py
Verification business logic service

Features:
- Check verification status
- Assign roles after verification
- Handle re-verification requirements
- Preserve and restore roles
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

import discord
from sqlalchemy import select

from ..db.database import get_session
from ..db.models import User, UserVerificationData
from ..util.config_loader import Config

logger = logging.getLogger(__name__)


class VerificationService:
    """Manage verification states and role assignments"""
    
    def __init__(self, config: Config):
        self.config = config
    
    async def is_verified(self, discord_id: int) -> bool:
        """Check if user is verified and not requiring re-verification"""
        async with get_session() as session:
            result = await session.execute(
                select(UserVerificationData).where(
                    UserVerificationData.discord_id == discord_id
                )
            )
            ver_data = result.scalar_one_or_none()
            
            if not ver_data:
                return False
            
            # Check if re-verification is required
            if ver_data.reverification_required:
                return False
            
            return True
    
    async def requires_reverification(self, discord_id: int) -> Tuple[bool, Optional[str]]:
        """
        Check if user requires re-verification.
        
        Returns: (requires, reason)
        """
        async with get_session() as session:
            result = await session.execute(
                select(UserVerificationData).where(
                    UserVerificationData.discord_id == discord_id
                )
            )
            ver_data = result.scalar_one_or_none()
            
            if not ver_data:
                return (False, None)
            
            return (ver_data.reverification_required, ver_data.reverification_reason)
    
    async def save_verification_data(
        self,
        discord_id: int,
        cas_data: dict,
        is_reverification: bool = False
    ):
        """
        Save or update user verification data.
        
        Creates/updates both User and UserVerificationData records.
        """
        async with get_session() as session:
            # Extract CAS data
            login = cas_data.get("login", "").lower()
            email = cas_data.get("mail", "")
            first_name = cas_data.get("givenName", "")
            last_name = cas_data.get("sn", "")
            full_name = cas_data.get("cn", f"{first_name} {last_name}").strip()
            
            # Determine user type (from old working code logic)
            groups = cas_data.get("groups", [])
            affiliations = cas_data.get("eduPersonAffiliation", [])
            user_type = self._determine_user_type(groups, affiliations)
            
            # Update User record
            result = await session.execute(
                select(User).where(User.discord_id == discord_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                user = User(
                    discord_id=discord_id,
                    login=login,
                    activity=1,
                    type=user_type,
                    real_name=full_name,
                    attributes=cas_data.get("attributes", {}),
                    verified_at=datetime.now(timezone.utc),
                    is_bot=False
                )
                session.add(user)
            else:
                user.login = login
                user.activity = 1
                user.type = user_type
                user.real_name = full_name
                user.attributes = cas_data.get("attributes", {})
                user.verified_at = datetime.now(timezone.utc)
            
            # Update UserVerificationData
            result = await session.execute(
                select(UserVerificationData).where(
                    UserVerificationData.discord_id == discord_id
                )
            )
            ver_data = result.scalar_one_or_none()
            
            now = datetime.now(timezone.utc)
            
            if not ver_data:
                ver_data = UserVerificationData(
                    discord_id=discord_id,
                    cas_login=login,
                    cas_real_name=full_name,
                    cas_email=email,
                    verified_at=now,
                    last_reverified_at=now,
                    reverification_required=False
                )
                session.add(ver_data)
            else:
                ver_data.cas_login = login
                ver_data.cas_real_name = full_name
                ver_data.cas_email = email
                ver_data.last_reverified_at = now
                
                if is_reverification:
                    ver_data.reverification_required = False
                    ver_data.reverification_reason = None
                    ver_data.reverification_wave_id = None
                
                ver_data.updated_at = now
            
            await session.commit()
            
            logger.info(f"Saved verification data for user {discord_id} (login: {login})")
    
    def _determine_user_type(self, groups: list, affiliations: list) -> int:
        """
        Determine if user is student (0) or teacher (2).
        Uses logic from working old bot.
        """
        teacher_affiliations = ["employee", "faculty", "staff", "teacher"]
        for affiliation in affiliations:
            if any(ta in affiliation.lower() for ta in teacher_affiliations):
                logger.debug(f"User classified as teacher based on affiliation: {affiliation}")
                return 2
        
        teacher_groups = ["employees", "staff", "faculty", "teachers"]
        for group in groups:
            if any(tg in group.lower() for tg in teacher_groups):
                logger.debug(f"User classified as teacher based on group: {group}")
                return 2
        
        logger.debug("User classified as student (default)")
        return 0
    
    async def assign_verified_roles(
        self, 
        member: discord.Member, 
        cas_login: str
    ):
        """Assign appropriate roles based on CAS login and user type"""
        
        # Get user type from database
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.discord_id == member.id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                logger.warning(f"User {member.id} not found in database during role assignment")
                return
            
            user_type = user.type
        
        roles_to_add = []
        
        if user_type == 2:  # Teacher
            teacher_role = member.guild.get_role(self.config.teacher_role_id)
            if teacher_role:
                roles_to_add.append(teacher_role)
                logger.debug(f"Adding teacher role to {member.id}")
        else:  # Student (default)
            student_role = member.guild.get_role(self.config.student_role_id)
            if student_role:
                roles_to_add.append(student_role)
                logger.debug(f"Adding student role to {member.id}")
        
        # Add roles
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="Verified via CAS")
                logger.info(f"Assigned {len(roles_to_add)} roles to {member.id}")
            except discord.Forbidden:
                logger.error(f"Missing permissions to assign roles to {member.id}")
            except Exception as e:
                logger.error(f"Failed to assign roles to {member.id}: {e}")
    
    async def preserve_roles(self, member: discord.Member):
        """Preserve user's roles before removing them for re-verification"""
        async with get_session() as session:
            result = await session.execute(
                select(UserVerificationData).where(
                    UserVerificationData.discord_id == member.id
                )
            )
            ver_data = result.scalar_one_or_none()
            
            if not ver_data:
                logger.warning(f"Cannot preserve roles for {member.id} - no verification data")
                return
            
            # Save current roles (excluding @everyone)
            role_ids = [r.id for r in member.roles if r.id != member.guild.default_role.id]
            
            ver_data.preserved_roles = {
                "role_ids": role_ids,
                "preserved_at": datetime.now(timezone.utc).isoformat()
            }
            
            await session.commit()
            
            logger.info(f"Preserved {len(role_ids)} roles for user {member.id}")
    
    async def restore_roles(self, member: discord.Member):
        """Restore user's preserved roles after re-verification"""
        async with get_session() as session:
            result = await session.execute(
                select(UserVerificationData).where(
                    UserVerificationData.discord_id == member.id
                )
            )
            ver_data = result.scalar_one_or_none()
            
            if not ver_data or not ver_data.preserved_roles:
                # No preserved roles, assign based on user type
                logger.debug(f"No preserved roles for {member.id}, assigning default roles")
                await self.assign_verified_roles(member, ver_data.cas_login if ver_data else "")
                return
            
            # Restore preserved roles
            role_ids = ver_data.preserved_roles.get("role_ids", [])
            roles_to_add = []
            
            for role_id in role_ids:
                role = member.guild.get_role(role_id)
                if role:
                    roles_to_add.append(role)
            
            if roles_to_add:
                try:
                    await member.add_roles(*roles_to_add, reason="Roles restored after re-verification")
                    logger.info(f"Restored {len(roles_to_add)} roles to {member.id}")
                    
                    # Clear preserved roles
                    ver_data.preserved_roles = None
                    await session.commit()
                    
                except discord.Forbidden:
                    logger.error(f"Missing permissions to restore roles to {member.id}")
                except Exception as e:
                    logger.error(f"Failed to restore roles to {member.id}: {e}")
    
    async def require_reverification(
        self, 
        discord_id: int, 
        reason: str,
        wave_id: Optional[int] = None
    ):
        """Mark user as requiring re-verification"""
        async with get_session() as session:
            result = await session.execute(
                select(UserVerificationData).where(
                    UserVerificationData.discord_id == discord_id
                )
            )
            ver_data = result.scalar_one_or_none()
            
            if not ver_data:
                logger.warning(f"No verification data for user {discord_id}")
                return
            
            ver_data.reverification_required = True
            ver_data.reverification_reason = reason
            ver_data.reverification_requested_at = datetime.now(timezone.utc)
            ver_data.reverification_wave_id = wave_id
            
            await session.commit()
            
            logger.info(f"User {discord_id} marked for re-verification: {reason}")