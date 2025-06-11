# ARTEX ASSURANCES AI Agent

## 🚧 Project Status: Alpha 🚧
This project is currently in an alpha development stage. Core functionalities are being built and refined. Expect changes and potential instabilities.

## Overview
The ARTEX Assurances AI Agent, "Jules," is a sophisticated voice-enabled and API-driven assistant designed to help clients and prospects of ARTEX ASSURANCES, an insurance brokerage. It leverages Google Gemini for natural language understanding and generation, interacts with a MySQL database for client and policy information, and includes a Proof-of-Concept (PoC) for real-time communication via LiveKit. The project also features a FastAPI backend for API interactions.

## Key Features
*   **Conversational AI**: Engages in natural conversations in French, powered by Google Gemini 1.5 Flash.
*   **Voice I/O**:
    *   **ASR (Speech-to-Text)**: Advanced speech recognition for French voice input (via local microphone in CLI mode). Includes silence detection and clear signaling of ASR states.
    *   **TTS (Text-to-Speech)**: High-quality voice output with caching. Uses Google Cloud Text-to-Speech if configured, with gTTS as a fallback.
*   **Database Interaction**:
    *   Connects to a MySQL database (`extranet` schema provided by user).
    *   SQLAlchemy ORM with Alembic for migrations.
    *   Agent can retrieve contract details and open new claim records (for Artex's internal tracking) using Gemini Function Calling.
*   **LiveKit Integration (Proof-of-Concept)**:
    *   Foundational setup for a Python gRPC client to interact with LiveKit for real-time communication.
    *   Agent can (conceptually) join rooms, publish its TTS audio, and process incoming audio via ASR.
    *   Includes welcome messages and silence-based hangup logic in the participant handler.
    *   (Note: Actual audio streaming over LiveKit gRPC client is still simulated; full WebRTC integration is a future step).
*   **API Backend (FastAPI)**:
    *   Basic FastAPI application structure (`src/main.py`).
    *   `GET /healthz` endpoint for monitoring database and Gemini connectivity.
    *   `POST /webhook/livekit` placeholder endpoint for receiving LiveKit server events.
    *   CORS configured for frontend development.
*   **Configuration Management**: Securely managed via `.env` files (with `.env.template` providing guidance).
*   **Robust Agent Logic**:
    *   Handles ambiguous user queries by requesting clarification (`[CLARIFY]` tag).
    *   Can perform a simulated handoff to a human agent if necessary (`[HANDOFF]` tag).
*   **Project Scaffolding**: Uses `pyproject.toml` for packaging and pinned dependencies in `requirements.txt` for reproducible environments.

## Project Structure
```
artex_agent/
├── alembic.ini
├── Dockerfile
├── docker-compose.yml
├── init_db.py
├──migrations/                     # Alembic migration scripts
│   ├── versions/
│   └── env.py
├── prompts/
│   └── system_context.txt        # System prompt for Gemini
├── pyproject.toml
├── README.md
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── agent.py                  # Main CLI agent logic
│   ├── asr.py                    # Speech-to-Text service
│   ├── database_models.py        # SQLAlchemy ORM models
│   ├── database_repositories.py  # Database repository classes
│   ├── database.py               # DB engine, session factory
│   ├── gemini_client.py          # Gemini API client
│   ├── gemini_tools.py           # Gemini function call definitions
│   ├── livekit_integration.py    # LiveKit Server SDK utilities (e.g., token generation)
│   ├── livekit_participant_handler.py # LiveKit client participant logic (gRPC based, conceptual)
│   ├── livekit_rtc_stubs/        # Placeholder for LiveKit gRPC stubs
│   │   ├── __init__.py
│   │   ├── livekit_rtc_pb2.py    # (Placeholder)
│   │   ├── livekit_rtc_pb2_grpc.py # (Placeholder)
│   │   └── README_FOR_GRPC_STUBS.txt
│   ├── logging_config.py         # Structlog configuration (to be fully integrated)
│   ├── main.py                   # FastAPI application
│   └── tts.py                    # Text-to-Speech service
├── tests/
│   └── test_agent.py             # Placeholder for tests
└── .env.template                   # Template for environment variables
```

## Setup and Installation

1.  **Prerequisites**:
    *   Python 3.9+
    *   `pip` and `venv` (recommended for virtual environments)
    *   Access to a MySQL 8 server.
    *   Access to a LiveKit server (for LiveKit features).
    *   Google Cloud account with Gemini API enabled and potentially Google Cloud Text-to-Speech API enabled.
    *   System dependencies for `PyAudio` (e.g., `portaudio19-dev` on Debian/Ubuntu) and `pydub` (`ffmpeg`).
        ```bash
        # Example for Debian/Ubuntu:
        # sudo apt-get update
        # sudo apt-get install -y portaudio19-dev ffmpeg
        ```

2.  **Clone the Repository (if applicable)**:
    ```bash
    # git clone <repository_url>
    # cd artex_agent
    ```

3.  **Create and Activate a Virtual Environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

4.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    # For editable install (useful for development):
    # pip install -e .
    ```

5.  **Configure Environment Variables**:
    *   Copy the template: `cp .env.template .env`
    *   Edit the `.env` file with your actual credentials and configurations. Refer to the comments in `.env.template` for details on each variable (e.g., `GEMINI_API_KEY`, `DATABASE_URL`, LiveKit settings, Google Cloud TTS settings).
    *   If using Google Cloud services (like Text-to-Speech), ensure `GOOGLE_APPLICATION_CREDENTIALS` points to your valid service account JSON key file.

6.  **Database Setup**:
    *   Ensure your MySQL server is running and accessible.
    *   Update the `DATABASE_URL` in your `.env` file.
    *   **Initialize Schema**: You have two options:
        *   **Using `init_db.py` (quick setup for dev):**
            ```bash
            python init_db.py
            ```
            This will create all tables based on the current models. Set `DROP_TABLES_FIRST=true` in `.env` if you want to drop existing tables before creation.
        *   **Using Alembic Migrations (recommended for managing schema changes):**
            1.  Review `alembic.ini` and `migrations/env.py` (should be pre-configured to use `DATABASE_URL` from `.env`).
            2.  Apply migrations:
                ```bash
                alembic upgrade head
                ```
                The initial migration `0001_create_artex_schema.py` will set up the tables.

7.  **LiveKit gRPC Stubs (Developer Task)**:
    *   For full LiveKit client functionality, Python gRPC stubs need to be generated from LiveKit's `.proto` files. Refer to `src/livekit_rtc_stubs/README_FOR_GRPC_STUBS.txt` for instructions. This is a manual developer step. The current implementation uses placeholders for these stubs.

## How to Run

### 1. Command-Line Interface (CLI) Agent
The CLI agent allows direct voice or text interaction.
```bash
python src/agent.py
```
Optional arguments:
*   `--mic-index <index>`: Specify the microphone device index to use.
*   `--livekit-room <room_name> --livekit-identity <identity>`: Run in LiveKit PoC mode (connects to LiveKit, simulated audio I/O via CLI text).

### 2. FastAPI Application (API Server)
The FastAPI application exposes API endpoints.
```bash
# Ensure .env file is populated, especially for DATABASE_URL and GEMINI_API_KEY
# Run from the project root (artex_agent/)
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```
*   The API will be available at `http://localhost:8000`.
*   Interactive API documentation (Swagger UI) at `http://localhost:8000/docs`.
*   Health check: `http://localhost:8000/healthz`.

## Basic Usage

*   **CLI Agent**: Start `agent.py`. You can speak when prompted or type 'texte' to switch to text input mode. Type 'voix' to switch back to voice. Type 'quitter' to exit. The agent can answer questions, get contract details, or open claims based on its programming.
*   **API**: Interact with the exposed endpoints (e.g., `/healthz`, `/webhook/livekit`). More business logic endpoints will be added in the future.

## Testing
Refer to `TESTING_GUIDE.md` for detailed manual testing instructions for all features.
Automated tests (using `pytest`) are planned for future development.

## Future Development Ideas (from User's Roadmap)
This project is evolving. Future enhancements based on the user's 11-point plan include:
*   Full implementation of LiveKit client-side gRPC for real-time audio streaming.
*   Advanced error handling and structured logging with Structlog & Sentry.
*   Containerization with Docker and Docker Compose (including MySQL service).
*   CI/CD workflows with GitHub Actions (linting, formatting, testing).
*   Comprehensive unit and integration tests.
*   Makefiles for development tasks.
*   Observability with Prometheus metrics and centralized logging.
*   And much more as per the detailed roadmap.

## Contributing
(Placeholder for contribution guidelines)

## License
(Placeholder - e.g., MIT License. Confirm and update)
Currently, `pyproject.toml` suggests MIT License.
