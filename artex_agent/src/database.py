import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.sql import text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

# Load .env file at module level if this script is run directly
# In the main application (agent.py), load_dotenv() is called at its entry point.
if __name__ == "__main__" or not os.getenv("GEMINI_API_KEY"): # Simple check if .env might not be loaded
    load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
db_engine_instance = None # Module-level engine instance

if not DATABASE_URL:
    print("CRITICAL: DATABASE_URL environment variable not set. Database functionality will be unavailable.")
    # db_engine_instance will remain None
else:
    try:
        db_engine_instance = create_async_engine(DATABASE_URL, echo=False) # Set echo=True for SQL debugging
        print(f"Database engine initialized with URL: {DATABASE_URL[:DATABASE_URL.find('@') + 1 if '@' in DATABASE_URL else 30]}...") # Avoid printing full creds
    except Exception as e:
        print(f"CRITICAL: Failed to create database engine: {e}")
        # db_engine_instance will remain None

AsyncSessionFactory = None
if db_engine_instance:
    AsyncSessionFactory = async_sessionmaker(
        bind=db_engine_instance,
        expire_on_commit=False, # Common for async, prevents attributes being expired after commit
        class_=AsyncSession
    )
    print("AsyncSessionFactory created.")
else:
    print("AsyncSessionFactory not created because database engine initialization failed.")

# Function to get a DB session (used by repositories or service layer)
async def get_db_session() -> AsyncSession:
    if not AsyncSessionFactory:
        raise Exception("Database session factory not configured. Check DATABASE_URL and engine initialization.")
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit() # Commit at the end of a successful session block
        except SQLAlchemyError as e:
            await session.rollback()
            print(f"Database transaction rolled back due to: {e}")
            raise # Re-raise the exception to be handled by the caller
        except Exception as e:
            await session.rollback()
            print(f"An unexpected error occurred in get_db_session: {e}")
            raise
        finally:
            await session.close() # Ensure session is closed

# --- Repository-dependent functions (These were using direct engine access, now should use session) ---
# Refactoring these to use AsyncSession from the factory.
# The actual repository methods will handle the session.
# These functions below were examples and will be effectively replaced by repository calls.

async def get_policy_details_direct(session: AsyncSession, policy_id: str) -> dict | None:
    """
    Retrieves policy details for a given policy_id using a provided session.
    This is an example of how a repository method would use the session.
    """
    query = text("""
        SELECT policy_id, user_id, policy_type, start_date, end_date, premium_amount, status
        FROM policies
        WHERE policy_id = :policy_id
    """)
    try:
        result = await session.execute(query, {"policy_id": policy_id})
        row = result.fetchone()
        if row:
            return dict(row._mapping)
        return None
    except SQLAlchemyError as e:
        print(f"Error fetching policy details for {policy_id}: {e}")
        return None

async def update_user_preference_direct(session: AsyncSession, user_id: str, receive_updates: bool) -> bool:
    """
    Updates a user's preference using a provided session.
    Example of how a repository method would use the session.
    """
    query = text("""
        INSERT INTO user_preferences (user_id, receive_email_updates)
        VALUES (:user_id, :receive_updates)
        ON DUPLICATE KEY UPDATE receive_email_updates = :receive_updates;
    """)
    try:
        result = await session.execute(query, {"user_id": user_id, "receive_updates": receive_updates})
        # No explicit commit here, `get_db_session` handles it.
        return result.rowcount > 0
    except SQLAlchemyError as e:
        print(f"Error updating user preference for {user_id}: {e}")
        return False

# --- Test functions ---

async def main_test_runner():
    """Main async runner for all tests, using the session factory."""
    print("\n--- Testing Database Module with Session Factory ---")
    if not AsyncSessionFactory:
        print("Database not configured (AsyncSessionFactory is None). Cannot run tests.")
        return

    async with AsyncSessionFactory() as session: # Get a session from the factory
        # Test 1: Basic connection test using the new session
        try:
            print("\nTesting basic SELECT 1 with new session...")
            result = await session.execute(text("SELECT 1"))
            scalar_one = result.scalar_one()
            print(f"SUCCESS: Direct SELECT 1 result: {scalar_one}")
        except Exception as e:
            print(f"FAILURE: Basic SELECT 1 test failed: {e}")
            return # Stop further tests if basic connection fails

        # Test 2: Using a refactored/example direct function with session
        print("\nTesting get_policy_details_direct (example function)...")
        test_policy_id_exists = "POL123" # Assume this exists in your test DB
        details = await get_policy_details_direct(session, test_policy_id_exists)
        if details:
            print(f"SUCCESS: Policy {test_policy_id_exists} details: {details}")
        else:
            print(f"INFO: Policy {test_policy_id_exists} not found (or error occurred). This might be expected if DB is not pre-populated.")

        # Test 3: Example of using a repository (if repositories are in a separate file)
        # For this test, we'll assume database_repositories.py is available
        # and its classes take an AsyncSession.
        try:
            from .database_repositories import ClientRepository, UserPreferenceRepository # Local import for testing

            print("\nTesting ClientRepository.list_clients...")
            client_repo = ClientRepository(session)
            clients = await client_repo.list_clients(limit=2)
            if clients is not None: # list_clients returns a list, could be empty
                 print(f"SUCCESS: Found clients via repository (limit 2): {[(c.id, c.client_ref) for c in clients]}")
            else: # Should not happen unless there's an error in list_clients itself
                 print(f"FAILURE: client_repo.list_clients returned None")


            print("\nTesting UserPreferenceRepository.update_user_preference...")
            user_pref_repo = UserPreferenceRepository(session)
            test_user_id = "USER_TEST_001"

            print(f"Attempting to set receive_updates to True for {test_user_id}...")
            updated_pref_true = await user_pref_repo.update_user_preference(test_user_id, True)
            if updated_pref_true and updated_pref_true.receive_email_updates is True:
                print(f"SUCCESS & VERIFIED: Preference for {test_user_id} set to True: ID {updated_pref_true.id}, Value: {updated_pref_true.receive_email_updates}")
            else:
                print(f"FAILURE or VERIFICATION FAILED for setting True. Result: {updated_pref_true}")

            print(f"Attempting to set receive_updates to False for {test_user_id}...")
            updated_pref_false = await user_pref_repo.update_user_preference(test_user_id, False)
            if updated_pref_false and updated_pref_false.receive_email_updates is False:
                print(f"SUCCESS & VERIFIED: Preference for {test_user_id} set to False: ID {updated_pref_false.id}, Value: {updated_pref_false.receive_email_updates}")
            else:
                print(f"FAILURE or VERIFICATION FAILED for setting False. Result: {updated_pref_false}")

        except ImportError:
            print("\nSkipping repository tests: database_repositories.py not found (ensure it's in the same directory or adjust path).")
        except Exception as e:
            print(f"\nError during repository tests: {e}")

        # Note: The main_test_runner now implicitly tests commit/rollback via get_db_session
        # if it were used by the repository methods. Since repositories manage their own session
        # passed to them, they should call session.commit() or session.rollback() as appropriate.
        # The `get_db_session` provided here is a good pattern for service layer functions that
        # want to ensure a transaction block. For repositories, passing the session is fine.
        # The test runner uses AsyncSessionFactory directly here.

if __name__ == "__main__":
    # `load_dotenv()` is called at the top if this script is run directly.
    asyncio.run(main_test_runner())

    # Explicitly dispose of the engine when the script finishes, if it was created.
    async def dispose_engine_on_exit():
        if db_engine_instance:
            print("\nDisposing database engine...")
            await db_engine_instance.dispose()
            print("Database engine disposed.")

    asyncio.run(dispose_engine_on_exit())
