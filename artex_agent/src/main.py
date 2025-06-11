# Standard library imports
import os
import sys  # For sys.stderr in logging setup if needed, and sys.stdout for handler
import asyncio
from typing import Dict, Any, Optional

# Third-party imports
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from sqlalchemy.sql import text

# Load .env file: It's crucial to do this BEFORE other local modules are imported
# if those modules rely on environment variables at their import time.
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
else:
    pass

# Local application imports
# Setup logging first so other modules can use it if they log at import time
from .logging_config import setup_logging, get_logger

# Initialize logging immediately after imports and .env loading
setup_logging()
log = get_logger(__name__)

log.info("FastAPI application (main.py) starting up...")
if os.path.exists(dotenv_path):
    log.info(f".env file loaded successfully from {dotenv_path}")
else:
    log.warning(f".env file not found at {dotenv_path}. Relying on environment variables if set.")

# Now import other local modules that might use logging or env vars
from .database import AsyncSessionFactory, db_engine_instance
from .gemini_client import GeminiClient

# Create FastAPI app
app = FastAPI(
    title="ARTEX Assurances AI Agent API",
    description="API for interacting with the ARTEX AI Agent and managing related services.",
    version="0.2.0"
)

# CORS Configuration
ALLOWED_ORIGINS_STR = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080"
)
allowed_origins = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(",") if origin.strip()]
if not allowed_origins:
    allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
log.info(f"CORS allowed origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global Exception Handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("Unhandled exception occurred", error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )

# Test endpoint to verify exception handler
@app.get("/test-error", tags=["General"])
async def test_error():
    """Endpoint to trigger a test error for handler verification"""
    raise RuntimeError("This is a test error to verify the global exception handler.")

# Global service instances for FastAPI scope
gemini_client_instance: Optional[GeminiClient] = None

@app.on_event("startup")
async def startup_event():
    global gemini_client_instance
    log.info("FastAPI startup_event: Initializing services...")
    
    if not db_engine_instance or not AsyncSessionFactory:
        log.warning("Database engine or session factory not initialized from database.py during FastAPI startup. DB-dependent endpoints might fail.")
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
    db_status = "error"
    db_details = "not_checked"
    gemini_status = "error"
    gemini_details = "not_checked"

    # Check Database
    if AsyncSessionFactory and db_engine_instance:
        try:
            async with AsyncSessionFactory() as session:
                async with session.begin():
                    result = await session.execute(text("SELECT 1"))
                    if result.scalar_one() == 1:
                        db_status = "ok"
                        db_details = "Successfully executed SELECT 1."
                    else:
                        db_status = "error"
                        db_details = "SELECT 1 did not return 1."
        except Exception as e:
            log.error("Health Check: DB connection/query failed", error=str(e), exc_info=True)
            db_details = f"Exception: {type(e).__name__} - {str(e)}"
    else:
        db_status = "not_configured"
        db_details = "DB engine or session factory not initialized in database.py."
        log.warning("Health Check: DB status 'not_configured'.")

    # Check Gemini
    if gemini_client_instance:
        gemini_status = "ok"
        gemini_details = "GeminiClient instance available (initialized at startup)."
    else:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key or gemini_api_key == "YOUR_GEMINI_API_KEY_HERE":
            gemini_status = "not_configured"
            gemini_details = "GEMINI_API_KEY not set or is placeholder."
        else:
            gemini_status = "error"
            gemini_details = "GeminiClient failed to initialize during startup (API key set, but instance is None)."
        log.warning(f"Health Check: Gemini status '{gemini_status}'. Details: {gemini_details}")
    
    overall_status = "ok" if db_status == "ok" and gemini_status == "ok" else "error"
    
    response_payload = {
        "overall_status": overall_status,
        "dependencies": {
            "database": {"status": db_status, "details": db_details},
            "gemini": {"status": gemini_status, "details": gemini_details}
        }
    }
    log.info("Health check completed.", **response_payload)
    return response_payload

@app.post("/webhook/livekit", tags=["LiveKit"])
async def livekit_webhook_receiver(payload: Dict[str, Any], request: Request) -> Dict[str, str]:
    log.info("LiveKit webhook received.", payload_keys=list(payload.keys()))
    
    event_type = payload.get("event")
    if event_type:
        log.info(f"LiveKit Webhook Event Type: {event_type}", room_name=payload.get("room", {}).get("name"), participant_identity=payload.get("participant", {}).get("identity"))
    else:
        log.warning("LiveKit webhook received with no 'event' field.", payload_snippet=str(payload)[:200])

    return {"status": "webhook_received_successfully"}

# To run: uvicorn artex_agent.src.main:app --reload --log-level debug
# Access API: http://127.0.0.1:8000, Docs: /docs, Health: /healthz
