"""
bot/web/app.py
Web server for OAuth callbacks

Uses aiohttp for async web serving.
"""

import logging
from datetime import datetime

from aiohttp import web

from ..services.cas_service import CASService
from ..services.verification_service import VerificationService
from ..util.config_loader import Config

logger = logging.getLogger(__name__)


class OAuthWebServer:
    """OAuth callback web server"""
    
    def __init__(self, bot, config: Config, cas_service: CASService, verification_service: VerificationService):
        self.bot = bot
        self.config = config
        self.cas_service = cas_service
        self.verification_service = verification_service
        
        self.app = web.Application()
        self.request_count = 0
        self.setup_routes()
    
    def setup_routes(self):
        """Setup web server routes"""
        self.app.router.add_get("/", self.handle_root)
        self.app.router.add_get("/auth/callback", self.handle_callback)
        self.app.router.add_get("/callback", self.handle_callback)  # Alternate path
        self.app.router.add_get("/health", self.handle_health)
    
    async def handle_root(self, request: web.Request) -> web.Response:
        """Root endpoint - basic info"""
        self.request_count += 1
        
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Gatekeeper OAuth Server</title>
            <style>
                body { font-family: Arial; text-align: center; padding: 50px; }
                .status { color: #4CAF50; font-size: 24px; }
            </style>
        </head>
        <body>
            <div class="status">✓ Gatekeeper OAuth Server Running</div>
            <p>This server handles VSB Discord verification callbacks.</p>
        </body>
        </html>
        """
        
        return web.Response(text=html, content_type="text/html")
    
    async def handle_callback(self, request: web.Request) -> web.Response:
        """Handle OAuth callback from CAS"""
        self.request_count += 1
        
        ticket = request.query.get("ticket")
        state = request.query.get("state")
        client_ip = request.remote
        
        logger.info(f"OAuth callback received from {client_ip}")
        
        if not ticket:
            logger.warning("Callback missing ticket parameter")
            return web.Response(
                text=self.generate_error_page("Missing authentication ticket"),
                content_type="text/html",
                status=400
            )
        
        if not state:
            logger.warning("Callback missing state parameter")
            return web.Response(
                text=self.generate_error_page("Invalid authentication state"),
                content_type="text/html",
                status=400
            )
        
        # Process the authentication
        try:
            result = await self.cas_service.handle_callback(
                ticket=ticket,
                state=state,
                ip_address=client_ip
            )
            
            if not result.get("success"):
                error = result.get("error", "Unknown error")
                logger.error(f"Callback processing failed: {error}")
                return web.Response(
                    text=self.generate_error_page(error),
                    content_type="text/html",
                    status=400
                )
            
            # Success! Save verification data
            discord_id = result["discord_id"]
            guild_id = result["guild_id"]
            cas_data = result["cas_data"]
            is_reverification = result["is_reverification"]
            
            await self.verification_service.save_verification_data(
                discord_id=discord_id,
                cas_data=cas_data,
                is_reverification=is_reverification
            )
            
            # Assign roles
            guild = self.bot.get_guild(guild_id)
            member = guild.get_member(discord_id) if guild else None
            
            if member:
                if is_reverification:
                    # Restore preserved roles
                    await self.verification_service.restore_roles(member)
                else:
                    # Assign new roles
                    await self.verification_service.assign_verified_roles(
                        member,
                        cas_data.get("login", "")
                    )
            
            # Generate success page
            user_info = {
                "display_name": cas_data.get("cn", "User"),
                "login": cas_data.get("login", "unknown"),
                "linked_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            }
            
            logger.info(f"Successful verification for Discord user {discord_id}")
            
            return web.Response(
                text=self.generate_success_page(user_info),
                content_type="text/html"
            )
            
        except Exception as e:
            logger.error(f"Callback processing error: {e}", exc_info=True)
            return web.Response(
                text=self.generate_error_page("Internal server error during authentication"),
                content_type="text/html",
                status=500
            )
    
    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint"""
        self.request_count += 1
        
        health_data = {
            "status": "healthy",
            "service": "Gatekeeper OAuth Server",
            "requests_served": self.request_count,
            "bot_connected": self.bot.is_ready()
        }
        
        return web.json_response(health_data)
    
    def generate_success_page(self, user_info: dict) -> str:
        """Generate beautiful success page (from working old bot)"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authentication Successful - VSB Discord</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #333;
        }}
        
        .success-container {{
            background: white;
            padding: 3rem;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            text-align: center;
            max-width: 500px;
            width: 90%;
        }}
        
        .success-icon {{
            width: 80px;
            height: 80px;
            background: #4CAF50;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 2rem;
            font-size: 2.5rem;
        }}
        
        .success-title {{
            font-size: 2rem;
            color: #2c3e50;
            margin-bottom: 1rem;
            font-weight: 600;
        }}
        
        .success-message {{
            font-size: 1.1rem;
            color: #666;
            margin-bottom: 2rem;
            line-height: 1.6;
        }}
        
        .user-info {{
            background: #f8f9fa;
            padding: 1.5rem;
            border-radius: 12px;
            margin-bottom: 2rem;
        }}
        
        .user-detail {{
            margin-bottom: 0.5rem;
            font-size: 1rem;
        }}
        
        .user-detail strong {{
            color: #2c3e50;
        }}
        
        .close-instruction {{
            color: #666;
            font-style: italic;
            font-size: 0.9rem;
        }}
        
        .vsb-logo {{
            width: 100px;
            opacity: 0.7;
            margin-top: 2rem;
        }}
    </style>
</head>
<body>
    <div class="success-container">
        <div class="success-icon">
            ✅
        </div>
        
        <h1 class="success-title">Authentication Successful!</h1>
        
        <div class="success-message">
            Your VSB account has been successfully linked to Discord. You now have access to all verified features in the VSB Discord server.
        </div>
        
        <div class="user-info">
            <div class="user-detail"><strong>Name:</strong> {user_info.get('display_name', 'Not provided')}</div>
            <div class="user-detail"><strong>Login:</strong> {user_info.get('login', 'Not provided')}</div>
            <div class="user-detail"><strong>Status:</strong> Verified ✅</div>
            <div class="user-detail"><strong>Linked:</strong> {user_info.get('linked_at', 'Just now')}</div>
        </div>
        
        <p class="close-instruction">
            You can safely close this window and return to Discord.
        </p>
        
        <div class="vsb-logo">
            🎓 VSB-TUO
        </div>
    </div>
</body>
</html>
        """
    
    def generate_error_page(self, error_message: str) -> str:
        """Generate beautiful error page (from working old bot)"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Authentication Error - VSB Discord</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #ff7b7b 0%, #f06292 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #333;
        }}
        
        .error-container {{
            background: white;
            padding: 3rem;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            text-align: center;
            max-width: 500px;
            width: 90%;
        }}
        
        .error-icon {{
            width: 80px;
            height: 80px;
            background: #f44336;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 2rem;
            font-size: 2.5rem;
        }}
        
        .error-title {{
            font-size: 2rem;
            color: #2c3e50;
            margin-bottom: 1rem;
            font-weight: 600;
        }}
        
        .error-message {{
            font-size: 1.1rem;
            color: #666;
            margin-bottom: 2rem;
            line-height: 1.6;
            background: #fff3cd;
            padding: 1rem;
            border-radius: 8px;
            border-left: 4px solid #ffc107;
        }}
        
        .help-text {{
            color: #666;
            font-size: 0.95rem;
            line-height: 1.5;
            margin-bottom: 2rem;
        }}
        
        .contact-info {{
            background: #f8f9fa;
            padding: 1.5rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            font-size: 0.9rem;
        }}
        
        .retry-instruction {{
            color: #666;
            font-style: italic;
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-icon">
            ❌
        </div>
        
        <h1 class="error-title">Authentication Failed</h1>
        
        <div class="error-message">
            {error_message}
        </div>
        
        <div class="help-text">
            This error typically occurs when:<br>
            • The authentication link has expired<br>
            • Your VSB account credentials are invalid<br>
            • There was a temporary server issue
        </div>
        
        <div class="contact-info">
            <strong>Need help?</strong><br>
            Contact the Discord server administrators or try the authentication process again.
        </div>
        
        <p class="retry-instruction">
            You can close this window and try linking your account again from Discord.
        </p>
    </div>
</body>
</html>
        """
    
    async def start(self):
        """Start the web server"""
        try:
            runner = web.AppRunner(self.app)
            await runner.setup()
            site = web.TCPSite(runner, self.config.web_server_host, self.config.web_server_port)
            await site.start()
            
            logger.info(f"OAuth web server started on {self.config.web_server_host}:{self.config.web_server_port}")
        except Exception as e:
            logger.error(f"Failed to start web server: {e}", exc_info=True)
            raise
    
    async def stop(self):
        """Stop the web server"""
        logger.info("OAuth web server shutting down")