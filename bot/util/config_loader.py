"""
bot/util/config_loader.py
Environment configuration loader with validation
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Bot configuration from environment variables"""
    
    # Discord
    discord_token: str = Field(..., alias="DISCORD_TOKEN")
    guild_id: int = Field(..., alias="DISCORD_GUILD_ID")
    
    # Database
    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    db_name: str = Field(default="gatekeeper", alias="DB_NAME")
    db_user: str = Field(default="gatekeeper", alias="DB_USER")
    db_password: str = Field(..., alias="DB_PASSWORD")
    
    # OAuth/CAS - Legacy compatibility
    oauth_client_id: str = Field(..., alias="OAUTH_CLIENT_ID")
    oauth_client_secret: str = Field(..., alias="OAUTH_CLIENT_SECRET")
    oauth_base_url: str = Field(..., alias="OAUTH_BASE_URL")
    oauth_authorize_url: str = Field(..., alias="OAUTH_AUTHORIZE_URL")
    oauth_token_url: str = Field(..., alias="OAUTH_TOKEN_URL")
    oauth_userinfo_url: str = Field(..., alias="OAUTH_USERINFO_URL")
    oauth_redirect_uri: str = Field(..., alias="OAUTH_REDIRECT_URI")
    
    # CAS - From working implementation
    cas_server_url: str = Field(..., alias="CAS_SERVER_URL")
    cas_login_url: str = Field(..., alias="CAS_LOGIN_URL")
    cas_validate_url: str = Field(..., alias="CAS_VALIDATE_URL")
    cas_logout_url: str = Field(..., alias="CAS_LOGOUT_URL")
    service_url: str = Field(..., alias="SERVICE_URL")
    
    # Verification
    verification_channel_id: int = Field(..., alias="VERIFICATION_CHANNEL_ID")
    verification_state_expiry_minutes: int = Field(default=15, alias="VERIFICATION_STATE_EXPIRY_MINUTES")
    
    # Roles
    student_role_id: int = Field(..., alias="STUDENT_ROLE_ID")
    teacher_role_id: int = Field(..., alias="TEACHER_ROLE_ID")
    erasmus_role_id: Optional[int] = Field(default=None, alias="ERASMUS_ROLE_ID")
    host_role_id: Optional[int] = Field(default=None, alias="HOST_ROLE_ID")
    absolvent_role_id: Optional[int] = Field(default=None, alias="ABSOLVENT_ROLE_ID")
    admin_role_id: Optional[int] = Field(default=None, alias="ADMIN_ROLE_ID")
    moderator_role_id: Optional[int] = Field(default=None, alias="MODERATOR_ROLE_ID")
    
    # Annual Re-verification
    annual_reverification_enabled: bool = Field(default=True, alias="ANNUAL_REVERIFICATION_ENABLED")
    reverification_window_days: int = Field(default=14, alias="REVERIFICATION_WINDOW_DAYS")
    reverification_daily_batch_percent: float = Field(default=7.0, alias="REVERIFICATION_DAILY_BATCH_PERCENT")
    reverification_target_role: int = Field(..., alias="REVERIFICATION_TARGET_ROLE")
    
    # Web Server
    web_server_host: str = Field(default="0.0.0.0", alias="WEB_SERVER_HOST")
    web_server_port: int = Field(default=8080, alias="WEB_SERVER_PORT")
    web_server_external_url: str = Field(..., alias="WEB_SERVER_EXTERNAL_URL")
    
    # Security
    state_secret_key: str = Field(..., alias="STATE_SECRET_KEY")
    session_secret_key: str = Field(..., alias="SESSION_SECRET_KEY")
    
    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_channel_id: Optional[int] = Field(default=None, alias="LOG_CHANNEL_ID")
    
    # Optional: Tenor
    tenor_api_key: Optional[str] = Field(default=None, alias="TENOR_API_KEY")
    tenor_locale: str = Field(default="cs_CZ", alias="TENOR_LOCALE")
    tenor_content_filter: str = Field(default="medium", alias="TENOR_CONTENT_FILTER")
    
    @field_validator("state_secret_key", "session_secret_key")
    @classmethod
    def validate_secret_length(cls, v: str) -> str:
        """Ensure secrets are at least 32 characters"""
        if len(v) < 32:
            raise ValueError("Secret keys must be at least 32 characters long")
        return v
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v = v.upper()
        if v not in valid_levels:
            raise ValueError(f"Log level must be one of: {', '.join(valid_levels)}")
        return v
    
    @property
    def database_url(self) -> str:
        """Build asyncpg database URL"""
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def load_config(env_file: Optional[str] = None) -> Config:
    """
    Load configuration from environment file.
    
    Args:
        env_file: Path to .env file (default: .env in current directory)
    
    Returns:
        Config instance
    """
    if env_file:
        env_path = Path(env_file)
    else:
        # Try .env, .env.dev, .env.local
        for name in [".env", ".env.dev", ".env.local"]:
            env_path = Path(name)
            if env_path.exists():
                break
        else:
            raise FileNotFoundError("No .env file found")
    
    if not env_path.exists():
        raise FileNotFoundError(f"Environment file not found: {env_path}")
    
    load_dotenv(env_path)
    
    return Config()