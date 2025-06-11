# Standard library imports
import os
import sys # For sys.stderr in logging setup if needed, and sys.stdout for handler
import asyncio
from typing import Dict, Any, Optional

# Third-party imports
from fastapi import FastAPI, HTTPException, Request
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
# from livekit import WebhookReceiver # For actual signature verification (if implemented)


app = FastAPI(
    title="ARTEX Assurances AI Agent API",
    description="API for interacting with the ARTEX AI Agent and managing related services.",
    version="0.2.0" # Ensure this aligns with pyproject.toml
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
        log.error("Error initializing GeminiClient for FastAPI", error=str(e), exc_info=True)

    log.info("FastAPI startup_event: Service initialization checks complete.")

@app.on_event("shutdown")
async def shutdown_event():
    log.info("FastAPI application shutting down...")
    if db_engine_instance:
        log.info("Disposing database engine during FastAPI shutdown.")
        await db_engine_instance.dispose()
    log.info("FastAPI shutdown_event: Cleanup complete.")

@app.get("/", tags=["General"])
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
