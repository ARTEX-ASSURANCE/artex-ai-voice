import asyncio
import os
from dotenv import load_dotenv

# Add project root to Python path to allow direct execution of this script
# and correct module resolution for database and database_models.
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from artex_agent.src.database_models import Base
from artex_agent.src.database import db_engine_instance # Use the initialized engine from database.py

async def create_tables():
    """
    Creates all tables defined in Base.metadata using the configured engine.
    Optionally drops all tables first if DROP_TABLES_FIRST is set.
    """
    if not db_engine_instance:
        print("Database engine is not initialized. Ensure DATABASE_URL is set in .env and accessible.")
        return

    print(f"Attempting to connect to database and create tables...")
    try:
        async with db_engine_instance.begin() as conn:
            if os.getenv("DROP_TABLES_FIRST", "false").lower() == "true":
                print("Dropping all tables first (as per DROP_TABLES_FIRST)...")
                await conn.run_sync(Base.metadata.drop_all)
                print("Tables dropped.")

            print("Creating tables...")
            await conn.run_sync(Base.metadata.create_all)
            print("Database tables created (or verified to exist).")

            # You could add some initial data seeding here if needed for basic testing
            # from sqlalchemy.ext.asyncio import AsyncSession
            # from artex_agent.src.database_repositories import ClientRepository # Example
            # async with AsyncSession(db_engine_instance) as session:
            #     async with session.begin():
            #         client_repo = ClientRepository(session)
            #         # Check if a test client exists, if not create one
            #         # test_client = await client_repo.get_client_by_ref("TEST_CLIENT_001")
            #         # if not test_client:
            #         #     await client_repo.create_client({
            #         #         "client_ref": "TEST_CLIENT_001",
            #         #         "nom": "Test", "prenom": "Client",
            #         #         "email": "test@example.com"
            #         #     })
            #         #     print("Created initial test client.")
            #     await session.commit()


    except ConnectionRefusedError:
        print("Connection to the database was refused. Ensure the database server is running and accessible.")
        print(f"Attempted to connect using URL: {str(db_engine_instance.url)}")
    except Exception as e:
        print(f"An error occurred during table creation: {e}")
    finally:
        if db_engine_instance:
            await db_engine_instance.dispose()
            print("Database engine disposed after table creation attempt.")

if __name__ == "__main__":
    print("Initializing database schema...")
    # Load environment variables from .env file located in the parent directory
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        print(f".env file loaded from: {dotenv_path}")
    else:
        print(f"Warning: .env file not found at {dotenv_path}. Using existing environment variables if any.")

    # Ensure DATABASE_URL is loaded before running create_tables
    if not os.getenv("DATABASE_URL"):
        print("CRITICAL: DATABASE_URL not found. Cannot initialize database.")
    else:
        asyncio.run(create_tables())
