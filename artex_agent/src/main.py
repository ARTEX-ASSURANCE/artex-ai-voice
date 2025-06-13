# Standard library imports
import os
import sys # For sys.stderr in logging setup if needed, and sys.stdout for handler
import asyncio
from typing import Dict, Any, Optional

# Third-party imports
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse # Added import
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from sqlalchemy.sql import text

# Load .env file: It's crucial to do this BEFORE other local modules are imported
# if those modules rely on environment variables at their import time.
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    # Initial print to console before logging is fully set up, if needed for debug
    # print(f"FastAPI (main.py pre-log): Loaded .env from {dotenv_path}")
else:
    # print(f"FastAPI (main.py pre-log): .env file not found at {dotenv_path}.")
    pass

# Local application imports
# Setup logging first so other modules can use it if they log at import time
from .logging_config import setup_logging, get_logger

# Initialize logging immediately after imports and .env loading
# force_json=True can be used if API logs should always be JSON regardless of .env
# setup_logging(force_json=os.getenv("API_FORCE_JSON_LOGS", "false").lower() == "true")
setup_logging()
log = get_logger(__name__) # Logger for this module (main.py)

log.info("FastAPI application (main.py) starting up...")
if os.path.exists(dotenv_path):
    log.info(f".env file loaded successfully from {dotenv_path}")
else:
    log.warn(f".env file not found at {dotenv_path}. Relying on environment variables if set.")

# Now import other local modules that might use logging or env vars
from .database import AsyncSessionFactory, db_engine_instance
from .gemini_client import GeminiClient
from .api_models import ChatMessageRequest, ChatMessageResponse # Added for chat endpoint
from .agent_service import AgentService # Added for chat endpoint
from .gemini_tools import ARGO_AGENT_TOOLS # Direct import for tools
from .agent import load_prompt, DEFAULT_SYSTEM_PROMPT # Import loading mechanism and default prompt
# from livekit import WebhookReceiver # For actual signature verification (if implemented)

# Sentry SDK imports
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    # from sentry_sdk.integrations.asgi import SentryAsgiMiddleware # Not used directly if FastApiIntegration is primary
    SENTRY_SDK_AVAILABLE = True
    log.debug("Sentry SDK found and imported.")
except ImportError:
    SENTRY_SDK_AVAILABLE = False
    log.warn("Sentry SDK not installed. Sentry integration will be disabled.")


app = FastAPI(
    title="ARTEX Assurances AI Agent API",
    description="API for interacting with the ARTEX AI Agent and managing related services.",
    version="0.2.1" # Aligned with pyproject.toml
)

# CORS Configuration
ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080")
allowed_origins = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(",") if origin.strip()]
if not allowed_origins: # Default if env var is empty or misconfigured
    allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
log.info(f"CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global service instances for FastAPI scope
gemini_client_instance: Optional[GeminiClient] = None


# Custom Global Exception Handler
@app.exception_handler(Exception)
async def custom_global_exception_handler(request: Request, exc: Exception):
    """
    Custom global exception handler to catch all unhandled exceptions,
    log them with structlog (including traceback), and return a
    standardized JSON 500 error response.
    """
    log.error(
        "unhandled_api_exception",
        path=str(request.url),
        method=request.method,
        client_host=request.client.host if request.client else "unknown_client",
        error_type=type(exc).__name__,
        exc_info=exc
    )

    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."},
    )

# Test route for global exception handler
@app.get("/test-error", tags=["Testing Utilities"])
async def test_error_endpoint():
    """
    An endpoint to deliberately test the global exception handler.
    Calling this endpoint will raise a ValueError.
    """
    log.info("Test error endpoint '/test-error' called, deliberately raising an exception...")
    raise ValueError("This is a deliberate test exception to verify the global exception handler.")
    # This line below is unreachable but shows it's not a normal flow
    # return {"message": "You should not see this if the exception handler works."}

@app.on_event("startup")
async def startup_event():
    global gemini_client_instance
    log.info("FastAPI startup_event: Initializing services...")

    if not db_engine_instance or not AsyncSessionFactory:
        log.warn("Database engine or session factory not initialized from database.py during FastAPI startup. DB-dependent endpoints might fail.")
    else:
        log.info("Database engine and session factory appear to be initialized from database.py.")

    try:
        gemini_client_instance = GeminiClient()
        log.info("GeminiClient initialized successfully for FastAPI.")
    except Exception as e:
        log.error("Error initializing GeminiClient for FastAPI", error_str=str(e), exc_info=True) # Use error_str

    # Initialize Sentry
    if SENTRY_SDK_AVAILABLE:
        sentry_dsn = os.getenv("SENTRY_DSN")
        sentry_environment = os.getenv("SENTRY_ENVIRONMENT", "development") # Default to 'development'
        if sentry_dsn and sentry_dsn != "YOUR_SENTRY_DSN_HERE":
            try:
                sentry_sdk.init(
                    dsn=sentry_dsn,
                    integrations=[
                        FastApiIntegration(),
                    ],
                    traces_sample_rate=1.0,
                    profiles_sample_rate=1.0,
                    send_default_pii=False,
                    environment=sentry_environment,
                    # release="artex-agent@0.2.1" # Example, consider dynamic versioning
                )
                log.info("Sentry SDK initialized.", dsn_configured=True, environment=sentry_environment)
                # Optional: Test Sentry by sending a message
                # sentry_sdk.capture_message("Sentry initialized successfully during FastAPI startup!", level="info")
            except Exception as e:
                log.error("Failed to initialize Sentry SDK", error_str=str(e), exc_info=True) # Use error_str
        else:
            log.info("Sentry DSN not found or is placeholder. Sentry integration disabled.")
    else:
        # This log was already issued when SENTRY_SDK_AVAILABLE was set
        pass # log.warn("Sentry SDK is not installed. Sentry integration is disabled.")

    # Load system prompt for AgentService
    # (load_dotenv() is already called at the top of main.py)
    loaded_arthex_system_prompt_for_api = load_prompt("system_context.txt", default_prompt=DEFAULT_SYSTEM_PROMPT)
    if not loaded_arthex_system_prompt_for_api or loaded_arthex_system_prompt_for_api == DEFAULT_SYSTEM_PROMPT:
        log.warn("AgentService in FastAPI using default system prompt. Check 'system_context.txt' if custom prompt expected.")


    # Initialize AgentService
    if gemini_client_instance: # Only attempt if Gemini client itself initialized
        try:
            app.state.agent_service = AgentService(
                gemini_client_instance=gemini_client_instance,
                system_prompt_text=loaded_arthex_system_prompt_for_api, # Use directly loaded prompt
                artex_agent_tools_list=ARGO_AGENT_TOOLS  # Use directly imported tools
            )
            log.info("AgentService initialized and attached to app.state.")
        except Exception as e:
            log.error("Failed to initialize AgentService during startup.", error_str=str(e), exc_info=True)
            app.state.agent_service = None # Ensure it's None if init fails
    else:
        log.warn("GeminiClient not available, AgentService will not be initialized.")
        app.state.agent_service = None

    log.info("FastAPI startup_event: Service initialization checks complete.")

@app.on_event("shutdown")
async def shutdown_event():
    log.info("FastAPI application shutting down...")
    if db_engine_instance:
        log.info("Disposing database engine during FastAPI shutdown.")
        await db_engine_instance.dispose()
    log.info("FastAPI shutdown_event: Cleanup complete.")

# --- API Endpoints ---

@app.post("/chat/send_message", response_model=ChatMessageResponse, tags=["Chat"])
async def send_chat_message(request_data: ChatMessageRequest, request: Request) -> ChatMessageResponse:
    log.info("Chat message received.", session_id=request_data.session_id, conversation_id=request_data.conversation_id, message_length=len(request_data.message))

    agent_service_instance = getattr(request.app.state, "agent_service", None)

    if not agent_service_instance:
        log.error("AgentService not available in /chat/send_message endpoint.")
        # This error might be caught by the global exception handler, but raising HTTPException is more specific.
        raise HTTPException(status_code=503, detail="Service temporarily unavailable. Please try again later.")

    try:
        agent_text_reply, new_conv_id, _ = await agent_service_instance.get_reply(
            session_id=request_data.session_id,
            user_message=request_data.message,
            conversation_id=request_data.conversation_id
        )

        log.info("Agent reply generated for API.", conversation_id=new_conv_id, agent_response_length=len(agent_text_reply))
        return ChatMessageResponse(
            agent_response=agent_text_reply,
            conversation_id=new_conv_id
            # debug_info can be added if get_reply is updated to return it
        )
    except Exception as e:
        # Log the specific error here before it's caught by the global handler
        log.error("Error processing chat message in API endpoint /chat/send_message.",
                  error_str=str(e),
                  session_id=request_data.session_id,
                  conversation_id=request_data.conversation_id,
                  exc_info=True)
        # Let the global exception handler manage the response format
        raise # Re-raise for the global handler to catch and return a 500

@app.get("/", tags=["General"]) # Keep existing routes below new additions
async def read_root() -> Dict[str, str]:
    log.info("Root endpoint '/' accessed.")
    return {"message": "Welcome to the ARTEX Assurances AI Agent API"}

@app.get("/healthz", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    log.info("Health check endpoint '/healthz' accessed.")
    global gemini_client_instance
    db_status = "error"; db_details = "not_checked"
    gemini_status = "error"; gemini_details = "not_checked"

    # Check Database
    if AsyncSessionFactory and db_engine_instance:
        try:
            async with AsyncSessionFactory() as session:
                async with session.begin():
                    result = await session.execute(text("SELECT 1"))
                    if result.scalar_one() == 1:
                        db_status = "ok"; db_details = "Successfully executed SELECT 1."
                    else:
                        db_status = "error"; db_details = "SELECT 1 did not return 1."
        except Exception as e:
            log.error("Health Check: DB connection/query failed", error=str(e), exc_info=True)
            db_details = f"Exception: {type(e).__name__} - {str(e)}"
    else:
        db_status = "not_configured"; db_details = "DB engine or session factory not initialized in database.py."
        log.warn("Health Check: DB status 'not_configured'.")

    # Check Gemini
    if gemini_client_instance:
        gemini_status = "ok"; gemini_details = "GeminiClient instance available (initialized at startup)."
        # A light check could be added here if GeminiClient had a status method or similar
    else:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key or gemini_api_key == "YOUR_GEMINI_API_KEY_HERE":
            gemini_status = "not_configured"; gemini_details = "GEMINI_API_KEY not set or is placeholder."
        else:
            gemini_status = "error"; gemini_details = "GeminiClient failed to initialize during startup (API key set, but instance is None)."
        log.warn(f"Health Check: Gemini status '{gemini_status}'. Details: {gemini_details}")

    overall_status = "ok" if db_status == "ok" and gemini_status == "ok" else "error"

    response_payload = {
        "overall_status": overall_status,
        "dependencies": {
            "database": {"status": db_status, "details": db_details},
            "gemini": {"status": gemini_status, "details": gemini_details}
        }
    }
    log.info("Health check completed.", **response_payload) # Log the health status
    return response_payload

@app.post("/webhook/livekit", tags=["LiveKit"])
async def livekit_webhook_receiver(payload: Dict[str, Any], request: Request) -> Dict[str, str]:
    # log = get_logger("livekit_webhook") # Specific logger for this endpoint if needed
    log.info("LiveKit webhook received.", payload_keys=list(payload.keys())) # Log only keys for brevity

    event_type = payload.get("event")
    if event_type:
        log.info(f"LiveKit Webhook Event Type: {event_type}", room_name=payload.get("room", {}).get("name"), participant_identity=payload.get("participant", {}).get("identity"))
        # Actual event processing logic to be added here based on event_type
    else:
        log.warn("LiveKit webhook received with no 'event' field.", payload_snippet=str(payload)[:200])

    # Placeholder for signature verification from original snippet:
    # from livekit import WebhookReceiver
    # receiver = WebhookReceiver(os.getenv("LIVEKIT_API_KEY"), os.getenv("LIVEKIT_API_SECRET"))
    # try:
    #     raw_body = await request.body()
    #     event = await asyncio.get_event_loop().run_in_executor(None, receiver.receive, raw_body.decode(), request.headers.get("Authorization"))
    #     log.info("LiveKit Webhook Verified", event_name=event.event, room_name=event.room.name if event.room else "N/A")
    # except Exception as e:
    #     log.error("LiveKit Webhook signature verification failed", error=str(e), exc_info=True)
    #     raise HTTPException(status_code=400, detail="Invalid webhook signature")

    return {"status": "webhook_received_successfully"}

# To run: uvicorn artex_agent.src.main:app --reload --log-level debug
# Access API: http://127.0.0.1:8000, Docs: /docs, Health: /healthz
