import os
import asyncio
import sys  # For standalone test logging
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.sql import text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

# Import logging configuration
from .logging_config import get_logger  # Assuming it's in the same directory (src)
log = get_logger(__name__)

# Load .env file at module level if this script is run directly
# This is important for when this module is run standalone for testing.
# In the main application (agent.py or main.py), load_dotenv() is called at their entry points.
if __name__ == "__main__" or not os.getenv("DATABASE_URL"):  # Check if DATABASE_URL is missing
    # This path assumes database.py is in src/ and .env is in project root (artex_agent/)
    dotenv_path_for_standalone = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path_for_standalone):
        load_dotenv(dotenv_path=dotenv_path_for_standalone)
    else:
        pass

DATABASE_URL = os.getenv("DATABASE_URL")
db_engine_instance = None

if not DATABASE_URL:
    log.critical("DATABASE_URL environment variable not set. Database functionality will be unavailable.")
else:
    try:
        db_engine_instance = create_async_engine(
            DATABASE_URL,
            echo=os.getenv("DB_ECHO", "false").lower() == "true"
        )
        # Mask credentials in log output
        url_to_log = DATABASE_URL
        if "@" in DATABASE_URL:
            url_to_log = (
                DATABASE_URL.split("@")[0].split("://")[0]
                + "://********@"
                + DATABASE_URL.split("@")[1]
            )
        log.info("Database engine initialized.", db_url_masked=url_to_log)
    except Exception as e:
        log.critical("Failed to create database engine.", error=str(e), exc_info=True)

AsyncSessionFactory: Optional[async_sessionmaker] = None
if db_engine_instance:
    AsyncSessionFactory = async_sessionmaker(
        bind=db_engine_instance,
        expire_on_commit=False,
        class_=AsyncSession
    )
    log.info("AsyncSessionFactory created successfully.")
else:
    log.warn("AsyncSessionFactory not created because database engine initialization failed.")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    if not AsyncSessionFactory:
        log.error("Database session factory not configured. Cannot yield session.")
        raise Exception("Database session factory not configured. Check DATABASE_URL and engine initialization.")

    session: Optional[AsyncSession] = None
    try:
        session = AsyncSessionFactory()
        log.debug("Database session yielded from factory.", session_id=str(session)[-4:])
        yield session
        await session.commit()
        log.debug("Database session committed successfully.", session_id=str(session)[-4:])
    except SQLAlchemyError as e:
        log.error(
            "Database transaction rolled back due to SQLAlchemyError.",
            error=str(e),
            exc_info=True,
            session_id=str(session)[-4:] if session else None
        )
        if session:
            await session.rollback()
        raise
    except Exception as e:
        log.error(
            "An unexpected error occurred in get_db_session; transaction rolled back.",
            error=str(e),
            exc_info=True,
            session_id=str(session)[-4:] if session else None
        )
        if session:
            await session.rollback()
        raise
    finally:
        if session:
            await session.close()
            log.debug("Database session closed.", session_id=str(session)[-4:])


# Example direct DB functions (now using session, for testing or simple tasks)
async def get_policy_details_direct(session: AsyncSession, policy_id: str) -> Optional[dict]:
    log.debug("Executing get_policy_details_direct", policy_id=policy_id)
    query = text(
        "SELECT policy_id, user_id, policy_type, start_date, end_date, "
        "premium_amount, status FROM policies WHERE policy_id = :policy_id"
    )
    try:
        result = await session.execute(query, {"policy_id": policy_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None
    except SQLAlchemyError as e:
        log.error(
            "Error fetching policy details directly.",
            policy_id=policy_id,
            error=str(e),
            exc_info=True
        )
        return None

async def update_user_preference_direct(session: AsyncSession, user_id: str, receive_updates: bool) -> bool:
    log.debug(
        "Executing update_user_preference_direct",
        user_id=user_id,
        receive_updates=receive_updates
    )
    query = text(
        "INSERT INTO user_preferences (user_id, receive_email_updates) "
        "VALUES (:user_id, :receive_updates) "
        "ON DUPLICATE KEY UPDATE receive_email_updates = :receive_updates;"
    )
    try:
        result = await session.execute(query, {"user_id": user_id, "receive_updates": receive_updates})
        return result.rowcount > 0
    except SQLAlchemyError as e:
        log.error(
            "Error updating user preference directly.",
            user_id=user_id,
            error=str(e),
            exc_info=True
        )
        return False


# --- Main Test Runner for standalone execution ---
async def main_test_runner():
    log = get_logger("db_test_runner")
    log.info("--- Testing Database Module with Session Factory ---")

    if not AsyncSessionFactory:
        log.error("Database not configured (AsyncSessionFactory is None). Cannot run tests.")
        return

    # Test 1: Basic connection test
    try:
        log.info("Testing basic SELECT 1 with new session...")
        async with AsyncSessionFactory() as session:
            async with session.begin():
                result = await session.execute(text("SELECT 1"))
                scalar_one = result.scalar_one()
                log.info("SUCCESS: Direct SELECT 1 result.", result=scalar_one)
    except Exception as e:
        log.error("FAILURE: Basic SELECT 1 test failed.", error=str(e), exc_info=True)
        return

    # Test 2: get_policy_details_direct
    log.info("Testing get_policy_details_direct (example function)...")
    test_policy_id_exists = "POL123"
    try:
        async with AsyncSessionFactory() as session:
            async with session.begin():
                details = await get_policy_details_direct(session, test_policy_id_exists)
                if details:
                    log.info("SUCCESS: Policy details found.", policy_id=test_policy_id_exists, details=details)
                else:
                    log.info("INFO: Policy not found (or error occurred).", policy_id=test_policy_id_exists)
    except Exception as e:
        log.error("Error testing get_policy_details_direct.", policy_id=test_policy_id_exists, error=str(e), exc_info=True)

    # Test 3: Repository tests
    try:
        from .database_repositories import AdherentRepository, UserPreferenceRepository
        log.info("Testing AdherentRepository.list_adherents...")
        async with AsyncSessionFactory() as session:
            async with session.begin():
                adherent_repo = AdherentRepository(session)
                adherents = await adherent_repo.list_adherents(limit=2)
                log.info(
                    "SUCCESS: Adherents found via repository (limit 2).",
                    adherents=[(c.id_adherent, c.nom) for c in adherents]
                )
    except ImportError:
        log.warn("Skipping repository tests: database_repositories.py not found.")
    except Exception as e:
        log.error("Error during repository tests.", error=str(e), exc_info=True)

    log.info("--- Database Module Test Finished ---")


if __name__ == "__main__":
    # Minimal logging setup
    import logging, structlog
    structlog.configure(processors=[structlog.dev.ConsoleRenderer()])
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "DEBUG").upper(), stream=sys.stdout)
    log.info("Minimal logging re-configured for database.py standalone test.")

    asyncio.run(main_test_runner())

    async def dispose_engine_on_exit():
        if db_engine_instance:
            log.info("Disposing database engine from database.py __main__...")
            await db_engine_instance.dispose()
            log.info("Database engine disposed.")

    asyncio.run(dispose_engine_on_exit())
