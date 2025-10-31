"""
bot/services/cas_service.py
CAS/SAML SSO integration service

Features:
- Generate CAS authorization URLs
- Handle OAuth callbacks
- Validate CAS tickets (working implementation from old bot)
- Extract user information
"""

import hashlib
import logging
import secrets
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import aiohttp
from sqlalchemy import select

from ..db.database import get_session
from ..db.models import User, UserVerificationData, VerificationAudit, VerificationState
from ..util.config_loader import Config

logger = logging.getLogger(__name__)


class CASService:
    """Handle CAS/SAML OAuth flow and ticket validation"""
    
    def __init__(self, config: Config):
        self.config = config
        
        # CAS configuration (from working implementation)
        self.cas_server_url = config.cas_server_url
        self.cas_login_url = config.cas_login_url
        self.cas_validate_url = config.cas_validate_url
        self.cas_logout_url = config.cas_logout_url
        self.service_url = config.service_url
        
        # OAuth configuration (legacy compatibility)
        self.client_id = config.oauth_client_id
        self.client_secret = config.oauth_client_secret
        self.authorize_url = config.oauth_authorize_url
        self.token_url = config.oauth_token_url
        self.userinfo_url = config.oauth_userinfo_url
        self.redirect_uri = config.oauth_redirect_uri
        
        # Security
        self.state_secret = config.state_secret_key
        self.state_expiry_minutes = config.verification_state_expiry_minutes
    
    async def generate_verification_url(
        self, 
        discord_id: int, 
        guild_id: int,
        is_reverification: bool = False,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Generate CAS authorization URL and store state token.
        
        Returns: (auth_url, state_token)
        """
        
        # Generate secure state token
        state = secrets.token_urlsafe(32)
        state_hash = hashlib.sha256(
            f"{state}:{discord_id}:{self.state_secret}".encode()
        ).hexdigest()
        
        # Store state in database
        async with get_session() as session:
            expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=self.state_expiry_minutes
            )
            
            verification_state = VerificationState(
                state=state_hash,
                discord_id=discord_id,
                guild_id=guild_id,
                is_initial=not is_reverification,
                expires_at=expires_at,
                ip_address=ip_address,
                user_agent=user_agent
            )
            session.add(verification_state)
            await session.commit()
        
        # Build CAS login URL with service parameter
        service_url_with_state = f"{self.service_url}?state={state}"
        params = {"service": service_url_with_state}
        auth_url = f"{self.cas_login_url}?{urllib.parse.urlencode(params)}"
        
        logger.info(f"Generated verification URL for Discord user {discord_id}")
        
        return auth_url, state
    
    async def handle_callback(
        self, 
        ticket: str, 
        state: str,
        ip_address: Optional[str] = None
    ) -> dict:
        """
        Handle CAS callback - validate ticket and process user data.
        
        Returns dict with:
        - success: bool
        - discord_id: int (if success)
        - guild_id: int (if success)
        - cas_data: dict (if success)
        - is_reverification: bool (if success)
        - error: str (if failure)
        """
        
        try:
            # 1. Validate state and get Discord ID
            async with get_session() as session:
                # Hash the incoming state
                # We need to find the matching verification state
                # Since we don't know discord_id yet, we search for non-expired states
                result = await session.execute(
                    select(VerificationState).where(
                        VerificationState.expires_at > datetime.now(timezone.utc)
                    )
                )
                verification_states = result.scalars().all()
                
                matching_state = None
                discord_id = None
                
                # Find matching state by reconstructing hash
                for vs in verification_states:
                    test_hash = hashlib.sha256(
                        f"{state}:{vs.discord_id}:{self.state_secret}".encode()
                    ).hexdigest()
                    
                    if test_hash == vs.state:
                        matching_state = vs
                        discord_id = vs.discord_id
                        break
                
                if not matching_state:
                    logger.warning(f"Invalid or expired state: {state[:8]}...")
                    return {"success": False, "error": "Invalid or expired verification state"}
                
                guild_id = matching_state.guild_id
                is_reverification = not matching_state.is_initial
                
                # Clean up state immediately
                await session.delete(matching_state)
                await session.commit()
            
            # 2. Validate CAS ticket (using working implementation)
            cas_data = await self.validate_cas_ticket(ticket, state)
            
            if not cas_data:
                return {"success": False, "error": "Failed to validate CAS ticket"}
            
            # 3. Success - log audit trail
            await self._log_verification_audit(
                discord_id=discord_id,
                cas_data=cas_data,
                state_hash=matching_state.state,
                ticket=ticket,
                result="success",
                ip_address=ip_address
            )
            
            logger.info(f"Successful verification for Discord user {discord_id}")
            
            return {
                "success": True,
                "discord_id": discord_id,
                "guild_id": guild_id,
                "cas_data": cas_data,
                "is_reverification": is_reverification
            }
            
        except Exception as e:
            logger.error(f"Callback handling error: {e}", exc_info=True)
            
            # Log failure audit
            try:
                await self._log_verification_audit(
                    discord_id=None,
                    cas_data={},
                    state_hash=state[:64],
                    ticket=ticket,
                    result="failure",
                    error_message=str(e),
                    ip_address=ip_address
                )
            except:
                pass
            
            return {"success": False, "error": str(e)}
    
    async def validate_cas_ticket(self, ticket: str, state: str) -> Optional[dict]:
        """
        Validate CAS ticket and parse user info.
        Uses working implementation from old bot.
        """
        service_url_with_state = f"{self.service_url}?state={state}"
        params = {"ticket": ticket, "service": service_url_with_state}
        validate_url = f"{self.cas_validate_url}?{urllib.parse.urlencode(params)}"
        
        logger.debug(f"Validating CAS ticket at: {self.cas_validate_url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(validate_url, timeout=15) as resp:
                    xml_response = await resp.text()
            
            # Parse CAS XML response (v3 protocol)
            root = ET.fromstring(xml_response)
            ns = {"cas": "http://www.yale.edu/tp/cas"}
            
            success = root.find("cas:authenticationSuccess", ns)
            if success is None:
                failure = root.find("cas:authenticationFailure", ns)
                code = failure.attrib.get("code") if failure is not None else "UNKNOWN"
                msg = (failure.text or "").strip() if failure is not None else "CAS authentication failed"
                logger.error(f"CAS validation failed: {code} - {msg}")
                return None
            
            # Extract user data
            username = success.findtext("cas:user", default="", namespaces=ns)
            attributes = {}
            
            cas_attrs = success.find("cas:attributes", ns)
            if cas_attrs is not None:
                for child in cas_attrs:
                    tag = child.tag.split("}", 1)[-1]
                    attributes[tag] = (child.text or "").strip()
            
            user_info = {
                "uid": username,
                "login": username,
                "attributes": attributes,
                "mail": attributes.get("mail", ""),
                "givenName": attributes.get("givenName", ""),
                "sn": attributes.get("sn", ""),
                "cn": attributes.get("cn", ""),
                "groups": attributes.get("groups", "").split(",") if attributes.get("groups") else [],
                "eduPersonAffiliation": (
                    attributes.get("eduPersonAffiliation", "").split(",")
                    if attributes.get("eduPersonAffiliation") else []
                ),
            }
            
            logger.info(f"CAS ticket validated successfully for user: {username}")
            
            return user_info
            
        except ET.ParseError as e:
            logger.error(f"Failed to parse CAS XML response: {e}")
            return None
        except Exception as e:
            logger.error(f"CAS ticket validation error: {e}", exc_info=True)
            return None
    
    async def _log_verification_audit(
        self,
        discord_id: Optional[int],
        cas_data: dict,
        state_hash: str,
        ticket: str,
        result: str,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None
    ):
        """Log verification attempt to audit table"""
        async with get_session() as session:
            audit = VerificationAudit(
                discord_id=discord_id,
                login=cas_data.get("login", "unknown"),
                cas_username=cas_data.get("uid", "unknown"),
                state_sha256=state_hash,
                ticket_sha256=hashlib.sha256(ticket.encode()).hexdigest(),
                result=result,
                error_message=error_message
            )
            session.add(audit)
            await session.commit()