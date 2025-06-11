import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncConnection
from sqlalchemy.sql import text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

# Hypothetical Schema:
#
# Table: policies
# Columns:
#   policy_id VARCHAR(255) PRIMARY KEY
#   user_id VARCHAR(255)
#   policy_type VARCHAR(50) (e.g., 'auto', 'habitation', 'sante')
#   start_date DATE
#   end_date DATE
#   premium_amount DECIMAL(10, 2)
#   status VARCHAR(20) (e.g., 'active', 'expired', 'cancelled')
#
# Table: users (referenced by user_id in policies and user_preferences)
# Columns:
#   user_id VARCHAR(255) PRIMARY KEY
#   name VARCHAR(255)
#   email VARCHAR(255)
#   ... (other user details)
#
# Table: user_preferences
# Columns:
#   preference_id INT AUTO_INCREMENT PRIMARY KEY
#   user_id VARCHAR(255) UNIQUE # Assumes one preference row per user
#   receive_email_updates BOOLEAN DEFAULT TRUE
#   preferred_contact_method VARCHAR(50) (e.g., 'email', 'phone')

def get_db_engine():
    """
    Creates and returns an SQLAlchemy async engine using the DATABASE_URL from environment variables.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set. Please set it before running.")
    engine = create_async_engine(database_url)
    return engine

async def get_policy_details(engine, policy_id: str) -> dict | None:
    """
    Retrieves policy details for a given policy_id.
    """
    if not engine:
        print("Database engine not provided.")
        return None

    query = text("""
        SELECT policy_id, user_id, policy_type, start_date, end_date, premium_amount, status
        FROM policies
        WHERE policy_id = :policy_id
    """)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(query, {"policy_id": policy_id})
            row = result.fetchone()
            if row:
                # Manually create a dictionary from the row object (RowProxy)
                return dict(row._mapping) # Accessing _mapping gives the dict-like interface
            return None
    except SQLAlchemyError as e:
        print(f"Error fetching policy details for {policy_id}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred in get_policy_details: {e}")
        return None

async def update_user_preference(engine, user_id: str, receive_updates: bool) -> bool:
    """
    Updates a user's preference for receiving email updates.
    Assumes the user_preferences table has a UNIQUE constraint on user_id.
    This version attempts an UPDATE first, then an INSERT if no rows were affected (and rows_matched is supported).
    A more robust way for MySQL is INSERT ... ON DUPLICATE KEY UPDATE.
    """
    if not engine:
        print("Database engine not provided.")
        return False

    # Using INSERT ... ON DUPLICATE KEY UPDATE for atomicity
    # This query assumes `user_id` is a unique key in `user_preferences`.
    # `preference_id` is assumed to be an auto-incrementing primary key if it exists.
    query = text("""
        INSERT INTO user_preferences (user_id, receive_email_updates)
        VALUES (:user_id, :receive_updates)
        ON DUPLICATE KEY UPDATE receive_email_updates = :receive_updates;
    """)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(query, {"user_id": user_id, "receive_updates": receive_updates})
            await conn.commit()
            return result.rowcount > 0 # rowcount for INSERT/UPDATE can be 1 (insert/update) or 2 (update if value changed)
                                      # For ON DUPLICATE KEY UPDATE, it's 1 for insert, 2 for update, 0 if no change.
                                      # So > 0 is a reasonable check for success.
    except SQLAlchemyError as e:
        print(f"Error updating user preference for {user_id}: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred in update_user_preference: {e}")
        return False

async def get_user_preference(engine, user_id: str) -> dict | None:
    """
    Retrieves user preferences for a given user_id. (Helper for testing)
    """
    if not engine:
        print("Database engine not provided.")
        return None
    query = text("SELECT user_id, receive_email_updates FROM user_preferences WHERE user_id = :user_id")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(query, {"user_id": user_id})
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return None
    except SQLAlchemyError as e:
        print(f"Error fetching user preference for {user_id}: {e}")
        return None

async def test_db_operations(db_engine):
    print("\n--- Testing Database Operations ---")

    # Test get_policy_details
    print("\nTesting get_policy_details...")
    # Replace with a policy_id that should exist in your test DB, or one that shouldn't
    test_policy_id_exists = "POL123" # Assume this exists
    test_policy_id_not_exists = "POL999" # Assume this does not exist

    details_exist = await get_policy_details(db_engine, test_policy_id_exists)
    if details_exist:
        print(f"SUCCESS: Policy {test_policy_id_exists} details: {details_exist}")
    else:
        # This is not necessarily a failure of the function, but that the data isn't there.
        print(f"INFO: Policy {test_policy_id_exists} not found (or error occurred).")

    details_not_exist = await get_policy_details(db_engine, test_policy_id_not_exists)
    if not details_not_exist:
        print(f"SUCCESS: Policy {test_policy_id_not_exists} correctly not found (or error).")
    else:
        print(f"FAILURE: Policy {test_policy_id_not_exists} unexpectedly found: {details_not_exist}")

    # Test update_user_preference and get_user_preference
    print("\nTesting update_user_preference...")
    test_user_id = "USER001" # Assume this user exists in 'users' table

    # Initial state (optional, good for seeing change)
    initial_pref = await get_user_preference(db_engine, test_user_id)
    print(f"Initial preference for {test_user_id}: {initial_pref}")

    # Update to True
    print(f"Attempting to set receive_updates to True for {test_user_id}...")
    update_success_true = await update_user_preference(db_engine, test_user_id, True)
    if update_success_true:
        print(f"SUCCESS: update_user_preference returned True for setting True.")
        updated_pref_true = await get_user_preference(db_engine, test_user_id)
        if updated_pref_true and updated_pref_true.get("receive_email_updates") is True:
            print(f"VERIFIED: Preference for {test_user_id} is now True: {updated_pref_true}")
        else:
            print(f"VERIFICATION FAILED: Preference for {test_user_id} not updated to True. Current: {updated_pref_true}")
    else:
        print(f"FAILURE: update_user_preference returned False for setting True.")

    # Update to False
    print(f"Attempting to set receive_updates to False for {test_user_id}...")
    update_success_false = await update_user_preference(db_engine, test_user_id, False)
    if update_success_false:
        print(f"SUCCESS: update_user_preference returned True for setting False.")
        updated_pref_false = await get_user_preference(db_engine, test_user_id)
        if updated_pref_false and updated_pref_false.get("receive_email_updates") is False:
            print(f"VERIFIED: Preference for {test_user_id} is now False: {updated_pref_false}")
        else:
            print(f"VERIFICATION FAILED: Preference for {test_user_id} not updated to False. Current: {updated_pref_false}")
    else:
        print(f"FAILURE: update_user_preference returned False for setting False.")

async def main_test_runner():
    """Main async runner for all tests."""
    print("Testing database connection module...")
    load_dotenv()

    db_engine_instance = None
    try:
        db_engine_instance = get_db_engine()
        print(f"Database engine created for URL: {os.getenv('DATABASE_URL')}")

        # Original connection test
        async with db_engine_instance.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            scalar_result = result.scalar_one()
            print(f"Initial connection test (SELECT 1): SUCCESS - Result: {scalar_result}")

        # Test new DB operations
        await test_db_operations(db_engine_instance)

    except ValueError as ve:
        print(f"Configuration Error: {ve}")
    except Exception as e:
        print(f"An unexpected error occurred during database tests: {e}")
    finally:
        if db_engine_instance:
            await db_engine_instance.dispose()
            print("Database engine disposed.")

if __name__ == "__main__":
    asyncio.run(main_test_runner())
