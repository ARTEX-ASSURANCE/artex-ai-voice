# ARTEX ASSURANCES AI Agent "Jules"

## 🚧 Project Status: Alpha 🚧
This project is an advanced AI-driven assistant for ARTEX ASSURANCES. It's currently in active development, building towards a production-ready system. Core backend functionalities, API, and an MVP frontend are taking shape.

## Table of Contents
1.  [Overview](#overview)
2.  [Key Features](#key-features)
3.  [Technology Stack](#technology-stack)
4.  [Project Structure](#project-structure)
5.  [Setup and Installation](#setup-and-installation)
    *   [Prerequisites](#prerequisites)
    *   [Backend Setup](#backend-setup)
    *   [Frontend Setup](#frontend-setup)
    *   [Database Initialization](#database-initialization)
6.  [Running the Application](#running-the-application)
    *   [Using Docker Compose (Recommended for Dev)](#using-docker-compose-recommended-for-dev)
    *   [Manual Backend Startup](#manual-backend-startup)
    *   [Manual Frontend Startup](#manual-frontend-startup)
    *   [CLI Agent](#cli-agent)
7.  [API Endpoints](#api-endpoints)
8.  [Testing](#testing)
9.  [Roadmap & Future Development](#roadmap--future-development)
10. [Contributing](#contributing)
11. [License](#license)

## Overview
"Jules" is an AI assistant for ARTEX ASSURANCES, designed to:
*   Provide information about insurance products (auto, home, health).
*   Assist clients with queries regarding their contracts.
*   Help initiate claim declarations for Artex's records (with processing by partner insurers).
*   Offer a seamless conversational experience in French via voice (CLI) and a web interface.

It leverages Google Gemini for NLU/NLG, interacts with a MySQL database for persistent storage, and is being built with a FastAPI backend and a React/TypeScript frontend. LiveKit integration for real-time voice communication is also a planned core feature (currently in PoC stage).

## Key Features

### Backend & Core Logic
*   **Advanced AI**: Powered by Google Gemini 1.5 Flash via a robust client (`GeminiClient`).
*   **Function Calling**: Gemini can invoke specific backend functions (e.g., `get_contrat_details`, `open_claim`) to interact with the database.
*   **Database Interaction**: SQLAlchemy ORM with asynchronous operations (`aiomysql`) for MySQL. Includes models for Adherents, Contrats, Formules, Garanties, and Sinistres (claims recorded by Artex).
*   **Migrations**: Alembic for database schema management.
*   **`AgentService`**: Centralized service layer for core agent logic, used by both API and CLI.
*   **Conversation History**: In-memory history management per conversation ID (for API).
*   **Robust Configuration**: Uses `.env` files for all secrets and configurations. Enhanced prompt loading with validation and fallbacks.
*   **Logging**: Structured JSON logging with `Structlog`, including PII masking.
*   **Error Handling**: Global exception handler in FastAPI and Sentry integration for error tracking.

### Voice I/O (for CLI & future LiveKit integration)
*   **ASR (Speech-to-Text)**: Modular `ASRService` (`src/asr.py`) using `speech_recognition` for French voice input, with silence detection and error signaling. Supports microphone selection.
*   **TTS (Text-to-Speech)**: Modular `TTSService` (`src/tts.py`) with caching, Google Cloud Text-to-Speech (high quality) and gTTS (fallback).

### LiveKit Integration (Proof-of-Concept Stage)
*   **Server-Side Utilities**: Token generation for participants (`src/livekit_integration.py`).
*   **Client Participant Handler**: Foundational structure for a Python gRPC client (`src/livekit_participant_handler.py`) to act as an agent in a LiveKit room, including conceptual audio I/O (TTS publishing via pydub, ASR input), welcome message, and silence-based hangup. (Note: gRPC stubs are currently placeholders).

### API Backend (FastAPI)
*   Located in `src/main.py`.
*   `POST /chat/send_message`: Main endpoint for frontend interaction.
*   `GET /healthz`: Monitors DB and Gemini connectivity.
*   `POST /webhook/livekit`: Placeholder for LiveKit server events.
*   CORS configured for frontend development.

### Frontend (MVP - React + TypeScript)
*   Located in `frontend/`.
*   Built with Vite, React, TypeScript, Tailwind CSS, and shadcn/ui.
*   **Theming**: Styled with ARTEX Assurances color palette.
*   **Core Chat UI**:
    *   Basic layout (header, message list, input area).
    *   Components for displaying messages (`ChatMessage.tsx`), listing messages with auto-scroll (`MessageList.tsx`), and user input (`InputArea.tsx`).
    *   Connects to the backend `/chat/send_message` API.
    *   Basic error display within the chat.

### Containerization
*   **Dockerfile**: Multi-stage Dockerfile for optimized and secure backend image.
*   **Docker Compose**: `docker-compose.yml` for easy local development setup of backend and MySQL database, including health checks.

## Technology Stack
*   **Backend**: Python 3.9+, FastAPI, Uvicorn, SQLAlchemy (asyncio), Alembic, Pydantic, Structlog, Sentry SDK.
*   **AI**: Google Gemini API.
*   **Database**: MySQL 8.
*   **Voice**: PyAudio, SpeechRecognition, gTTS, Google Cloud Text-to-Speech, pydub.
*   **Real-time Communication (PoC)**: LiveKit (Server SDK, gRPC concepts for client).
*   **Frontend**: Node.js, Vite, React, TypeScript, Tailwind CSS, shadcn/ui, clsx, tailwind-merge.
*   **Containerization**: Docker, Docker Compose.
*   **DevOps**: Git, (Future: GitHub Actions, Pre-commit hooks).

## Project Structure
```
artex_agent/
├── alembic.ini
├── Dockerfile
├── docker-compose.yml
├── frontend/                  # React + TypeScript Frontend
│   ├── public/
│   ├── src/
│   │   ├── components/       # Reusable UI components (ChatMessage, MessageList, InputArea)
│   │   │   └── ui/           # shadcn/ui base components (button, card, input, etc.)
│   │   ├── lib/              # Utility functions (e.g., cn for Tailwind)
│   │   ├── App.tsx           # Main application component
│   │   ├── main.tsx          # Frontend entry point
│   │   └── index.css         # Global styles & Tailwind directives
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── .env.template         # Frontend specific env vars (VITE_API_BASE_URL)
├── init_db.py                 # Script to initialize DB schema directly
├── migrations/                # Alembic migration scripts
│   ├── versions/
│   └── env.py
├── prompts/
│   └── system_context.txt     # System prompt for Gemini
├── pyproject.toml             # Project metadata and build configuration
├── README.md
├── requirements.txt           # Backend Python dependencies
├── src/                       # Backend Python source code
│   ├── __init__.py
│   ├── agent_service.py       # Core agent logic (Gemini, DB, history)
│   ├── agent.py               # CLI agent interaction logic
│   ├── api_models.py          # Pydantic models for FastAPI
│   ├── asr.py                 # Speech-to-Text service
│   ├── database_models.py     # SQLAlchemy ORM models
│   ├── database_repositories.py # Database repository classes
│   ├── database.py            # DB engine, session factory
│   ├── gemini_client.py       # Gemini API client
│   ├── gemini_tools.py        # Gemini function call definitions
│   ├── livekit_integration.py # LiveKit Server SDK utils (token gen)
│   ├── livekit_participant_handler.py # LiveKit client participant (gRPC, conceptual)
│   ├── livekit_rtc_stubs/     # For LiveKit gRPC generated stubs
│   │   └── README_FOR_GRPC_STUBS.txt
│   ├── logging_config.py      # Structlog configuration
│   ├── main.py                # FastAPI application entry point
│   └── tts.py                 # Text-to-Speech service
├── tests/                     # Backend tests (currently placeholder)
│   └── test_agent.py
└── .env.template                # Template for backend environment variables
```

## Setup and Installation

### Prerequisites
*   Python 3.9+
*   Node.js 18+ (for frontend development, includes npm/yarn)
*   Docker and Docker Compose (for containerized setup)
*   Access to a MySQL 8 server (can be run via Docker Compose).
*   LiveKit server (self-hosted or cloud, for LiveKit features).
*   Google Cloud Project with:
    *   Gemini API enabled.
    *   (Optional, for better TTS) Google Cloud Text-to-Speech API enabled.
    *   Service account key JSON file if using Google Cloud TTS.
*   System libraries:
    *   For PyAudio (backend voice input): `portaudio19-dev` (Debian/Ubuntu) or equivalent.
    *   For pydub (backend TTS audio processing): `ffmpeg` or `libav`.
    ```bash
    # Example for Debian/Ubuntu:
    # sudo apt-get update && sudo apt-get install -y portaudio19-dev ffmpeg
    ```

### Backend Setup
1.  **Clone Repository**: `git clone <your_repo_url> && cd artex_agent`
2.  **Create Backend Virtual Environment**:
    ```bash
    python -m venv venv_backend
    source venv_backend/bin/activate  # Or .venv_backend\Scripts\activate on Windows
    ```
3.  **Install Backend Dependencies**:
    ```bash
    pip install -r requirements.txt
    # For editable install (development):
    # pip install -e .
    ```
4.  **Configure Backend Environment (`.env` file)**:
    *   Copy `.env.template` to `.env` in the project root (`artex_agent/`).
    *   Edit `.env` with your actual credentials and configurations. Refer to comments in `.env.template` for details on `GEMINI_API_KEY`, `DATABASE_URL`, LiveKit settings, Google Cloud TTS, Sentry, etc.

### Frontend Setup
1.  **Navigate to Frontend Directory**: `cd frontend`
2.  **Create Frontend Virtual Environment (Optional, if managing Node versions with tools like nvm)**
3.  **Install Frontend Dependencies**:
    ```bash
    npm install  # or yarn install
    ```
4.  **Configure Frontend Environment (`frontend/.env`)**:
    *   Copy `frontend/.env.template` to `frontend/.env`.
    *   Edit `frontend/.env` and set `VITE_API_BASE_URL` (e.g., `http://localhost:8000` if backend runs locally on port 8000).

### Database Initialization
(Ensure MySQL is running and accessible, and `DATABASE_URL` in `.env` is correct).
*   **Option A (Alembic Migrations - Recommended)**:
    From the `artex_agent` root directory (with backend venv active):
    ```bash
    alembic upgrade head
    ```
*   **Option B (`init_db.py` - Quick Dev)**:
    From the `artex_agent` root directory (with backend venv active):
    ```bash
    python init_db.py
    ```
    (Set `DROP_TABLES_FIRST=true` in `.env` to clear existing tables first).
*   **Sample Data**: For full testing of database-dependent features (e.g., `get_contrat_details`), manually populate your database tables (`adherents`, `contrats`, `formules`, `garanties`, `formules_garanties`) with some sample data.

## Running the Application

### Using Docker Compose (Recommended for Local Development)
This is the easiest way to run the backend API and MySQL database together.
1.  Ensure Docker and Docker Compose are installed.
2.  Ensure your `.env` file in the `artex_agent` root is configured, especially `DATABASE_URL` (pointing to `mysql:3306`), `MYSQL_ROOT_PASSWORD`, `MYSQL_DATABASE_NAME`, `MYSQL_USER_NAME`, `MYSQL_USER_PASSWORD`.
3.  From the `artex_agent` root:
    ```bash
    docker-compose up --build
    ```
*   Backend API will be available at `http://localhost:8000`.
*   MySQL will be available on host port `3307` (connecting to container port `3306`).
*   The first time you run this, the database schema will be initialized by MySQL using scripts in `/docker-entrypoint-initdb.d/` if you place any `.sql`, `.sh` files there via `docker-compose.yml` volumes. For Alembic/`init_db.py`, you might need to run them against the containerized DB after it's up, or build them into an entrypoint script for the backend service. (Current `docker-compose.yml` does not auto-run migrations; this is a manual step or future enhancement).

### Manual Backend Startup (FastAPI with Uvicorn)
1.  Ensure backend venv is active and `.env` is configured.
2.  Ensure MySQL server is running and accessible.
3.  Run database migrations/initialization if not done.
4.  From the `artex_agent` root directory:
    ```bash
    uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
    ```
*   API at `http://localhost:8000`. Swagger UI docs at `http://localhost:8000/docs`.

### Manual Frontend Startup (Vite Dev Server)
1.  Navigate to `artex_agent/frontend/`.
2.  Ensure frontend dependencies are installed (`npm install` or `yarn install`).
3.  Ensure `frontend/.env` is configured with `VITE_API_BASE_URL`.
4.  Run the Vite development server:
    ```bash
    npm run dev  # or yarn dev
    ```
*   Frontend will typically be available at `http://localhost:5173` (or another port shown in console).

### CLI Agent
For direct command-line interaction with the agent's core logic (uses local mic/speakers).
1.  Ensure backend venv is active and `.env` is configured.
2.  From the `artex_agent` root directory:
    ```bash
    python src/agent.py
    ```
*   Optional arguments:
    *   `--mic-index <index>`: Specify microphone device index.
    *   `--livekit-room <room_name> --livekit-identity <identity>`: Run in (conceptual) LiveKit PoC mode.

## API Endpoints
(Refer to `http://localhost:8000/docs` when API is running for interactive documentation)

*   `GET /`: Welcome endpoint.
*   `GET /healthz`: Health check for DB and Gemini services.
*   `POST /chat/send_message`: Main endpoint for sending user messages and receiving agent responses.
    *   Request Body (`ChatMessageRequest`):
        ```json
        {
          "session_id": "string (unique per session)",
          "user_message": "string (user's text)",
          "conversation_id": "string (optional, for context)",
          "metadata": { "key": "value" } // Optional
        }
        ```
    *   Response Body (`ChatMessageResponse`):
        ```json
        {
          "assistant_message": "string (agent's reply)",
          "conversation_id": "string (current/new ID)",
          "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
          },
          "debug_info": null // Optional
        }
        ```
*   `POST /webhook/livekit`: Placeholder for receiving LiveKit server events.
*   `GET /test-error`: Intentionally raises an error to test global exception handler and Sentry.

## Testing
*   Manual testing: Refer to `TESTING_GUIDE.md` for detailed test cases covering all features.
*   Automated tests: Planned for future development using `pytest`. Currently, `tests/test_agent.py` is a placeholder.

## Roadmap & Future Development
This project aims to evolve into a production-ready voice assistant. Key areas for future development (based on user's original 11-point list and frontend requirements) include:
*   **Full LiveKit RTC Client Implementation**: Replacing gRPC placeholders with actual LiveKit RTC client logic for real-time audio streaming.
*   **Advanced Frontend Features**: Implementing all specified UI controls, theming options, accessibility features, i18n, and the detailed Debug/Trace Panel (with backend event emission).
*   **Comprehensive Testing**: Unit, integration, and potentially E2E tests.
*   **CI/CD**: GitHub Actions workflows for linting, formatting, testing, and deployment.
*   **Pre-commit Hooks**: For code quality checks before committing.
*   **Enhanced Docs & DX**: Makefiles for common dev tasks, Mermaid diagrams for architecture/flows.
*   **Observability**: Prometheus metrics for API performance, Gemini token usage, ASR/TTS timings. Centralized logging (e.g., shipping logs to Loki/Cloud Logging).
*   **Production Hardening**: Security enhancements, performance optimization, robust configuration management for different environments.

## Contributing
(Details to be added: contribution guidelines, code of conduct, etc.)

## License
This project is licensed under the MIT License. (Verify and update if different - `pyproject.toml` currently specifies MIT).
