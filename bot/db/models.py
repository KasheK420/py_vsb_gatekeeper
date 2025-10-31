"""
bot/db/models.py
Database models for Gatekeeper verification bot
FIXED VERSION - Corrects User.id references to User.discord_id
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, 
    Integer, JSON, String, Text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


class User(Base):
    __tablename__ = "users"

    # Primary key is now discord_id to match unified schema
    discord_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # Keep your business fields; types adjusted to unified table sizes
    login: Mapped[Optional[str]] = mapped_column(String(64), unique=True)  # can be nullable
    activity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    type: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verification: Mapped[Optional[str]] = mapped_column(String(64))
    real_name: Mapped[Optional[str]] = mapped_column(String(255))
    attributes: Mapped[Optional[dict]] = mapped_column(JSON)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class UserMetrics(Base):
    """Basic user statistics - KEEP EXISTING TABLE"""
    __tablename__ = "user_metrics"
    
    discord_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("users.discord_id", ondelete="CASCADE"), 
        primary_key=True
    )
    join_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bans: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class VerificationAudit(Base):
    """CAS verification audit trail - KEEP EXISTING TABLE"""
    __tablename__ = "verification_audit"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    login: Mapped[str] = mapped_column(String(64), nullable=False)
    cas_username: Mapped[str] = mapped_column(String(64), nullable=False)
    state_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    ticket_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(32), nullable=False)  # success/failure
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow, 
        nullable=False
    )


class BotLog(Base):
    __tablename__ = "bot_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    service: Mapped[Optional[str]] = mapped_column(String(64))     
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[dict]] = mapped_column(JSON)           
    guild_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    channel_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Optional fields for compatibility with other bots
    bot_name: Mapped[Optional[str]] = mapped_column(String(64))
    meta: Mapped[Optional[dict]] = mapped_column(JSON)


# ============================================
# NEW TABLES FOR GATEKEEPER
# ============================================


class VerificationState(Base):
    """Active verification states (pending OAuth flows)"""
    __tablename__ = "verification_states"
    
    state: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA256 hash
    discord_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("users.discord_id", ondelete="CASCADE"), 
        nullable=False
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    
    # Verification type
    is_initial: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Expiry
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow, 
        nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Metadata
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)


class UserVerificationData(Base):
    """Persistent verification data from CAS"""
    __tablename__ = "user_verification_data"
    
    discord_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("users.discord_id", ondelete="CASCADE"), 
        primary_key=True
    )
    
    # CAS data
    cas_login: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    cas_real_name: Mapped[Optional[str]] = mapped_column(String(150))
    cas_email: Mapped[Optional[str]] = mapped_column(String(150))
    
    # Verification status
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_reverified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Re-verification tracking
    reverification_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reverification_reason: Mapped[Optional[str]] = mapped_column(String(256))
    reverification_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reverification_wave_id: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Role preservation
    preserved_roles: Mapped[Optional[dict]] = mapped_column(JSON)
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow, 
        nullable=False
    )


class VerificationWave(Base):
    """Annual re-verification wave tracking"""
    __tablename__ = "verification_waves"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    
    # Wave configuration
    wave_name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    
    # Schedule
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)
    
    # Progress tracking
    total_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users_notified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Status
    status: Mapped[str] = mapped_column(
        String(32), 
        default="pending", 
        nullable=False
    )  # pending, active, completed
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow, 
        nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class VerificationWaveUser(Base):
    """Per-user tracking for verification waves"""
    __tablename__ = "verification_wave_users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wave_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("verification_waves.id", ondelete="CASCADE"), 
        nullable=False
    )
    discord_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("users.discord_id", ondelete="CASCADE"), 
        nullable=False
    )
    
    # Scheduling
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Status
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Reminders
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class UserStatusHistory(Base):
    """Track user join/leave/ban events"""
    __tablename__ = "user_status_history"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_id: Mapped[int] = mapped_column(
        BigInteger, 
        ForeignKey("users.discord_id", ondelete="CASCADE"), 
        nullable=False
    )
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    
    # Event type
    event_type: Mapped[str] = mapped_column(
        String(32), 
        nullable=False
    )  # join, leave, ban, unban, kick
    
    # Context
    roles_at_event: Mapped[Optional[dict]] = mapped_column(JSON)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    moderator_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow, 
        nullable=False
    )