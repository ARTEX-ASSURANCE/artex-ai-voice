# ARTEX ASSURANCES AI Agent - Manual Testing Guide

## 1. Setup and Configuration

Before running any tests, ensure your environment is correctly set up:

1.  **Prerequisites Met**:
    *   Python 3.9+ installed.
    *   `pip` and `venv` available.
    *   MySQL 8 server accessible.
    *   LiveKit server accessible (for LiveKit PoC tests).
    *   Google Cloud account with Gemini API and (optionally for better TTS) Google Cloud Text-to-Speech API enabled.
    *   System dependencies for PyAudio (e.g., `portaudio19-dev`) and pydub (`ffmpeg`) installed.

2.  **Project Setup**:
    *   Clone the repository (if applicable).
    *   Navigate to the `artex_agent` project root.
    *   Create and activate a Python virtual environment (e.g., `python -m venv venv && source venv/bin/activate`).
    *   Install dependencies: `pip install -r requirements.txt`.

3.  **Environment Variables (`.env` file)**:
    *   Copy `.env.template` to `.env`: `cp .env.template .env`.
    *   Edit `.env` and fill in all required credentials and configurations as described in the comments within `.env.template`. This includes:
        *   `GEMINI_API_KEY` (Required)
        *   `DATABASE_URL` (Required for DB features)
        *   `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` (Required for LiveKit PoC features)
        *   `GOOGLE_APPLICATION_CREDENTIALS` (Required if `TTS_USE_GOOGLE_CLOUD=true`)
        *   Other TTS settings, `LOG_LEVEL`, etc., as needed.

4.  **Database Initialization**:
    *   Ensure your MySQL server is running and the database specified in `DATABASE_URL` exists.
    *   Initialize the schema:
        *   **Option A (Recommended for schema management): Alembic Migrations**
            ```bash
            alembic upgrade head
            ```
        *   **Option B (Quick Dev Setup): `init_db.py`**
            ```bash
            python init_db.py
            ```
            (Set `DROP_TABLES_FIRST=true` in `.env` to clear existing tables first).
    *   **Sample Data**: For some database tests (e.g., retrieving existing contracts), you may need to manually insert sample data into the `adherents`, `formules`, `garanties`, `formules_garanties`, and `contrats` tables according to the schema in `database_models.py`.

5.  **Microphone & Speakers**: Ensure a working microphone and speakers are configured on your system for Voice I/O tests with the CLI agent.

## 2. Running the Agent / API

*   **CLI Agent**: `python src/agent.py [options]`
    *   Options: `--mic-index <index>`, `--livekit-room <name> --livekit-identity <id>`
*   **FastAPI Server**: `uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload` (from `artex_agent` root)

## 3. Test Case Series

### TC-GEN: General CLI Agent Interaction
(Run `python src/agent.py` for these tests)

*   **TC-GEN-1: Basic French Conversation & Persona**:
    *   Steps: Start agent. Greet it ("Bonjour Jules"). Ask a simple question ("Comment ça va?"). Ask about Artex ("Que fait ARTEX ASSURANCES?").
    *   Expected: Agent responds in French, maintains a professional and friendly persona (Jules from Artex).
*   **TC-GEN-2: Voice Input Mode**:
    *   Steps: Start agent (default voice mode). Speak a query when prompted.
    *   Expected: Agent transcribes speech, processes query, responds with voice and text.
*   **TC-GEN-3: Switch to Text Mode**:
    *   Steps: In voice mode, type `texte` when prompted for voice or after an ASR timeout/error.
    *   Expected: Agent switches to text input (`Vous (texte):`). Interactions continue via typed text.
*   **TC-GEN-4: Switch back to Voice Mode**:
    *   Steps: In text mode, type `voix`.
    *   Expected: Agent switches to voice input mode (`Parlez maintenant...`).
*   **TC-GEN-5: Handling Unclear Audio / ASR Timeout**:
    *   Steps: In voice mode, stay silent or mumble when prompted.
    *   Expected: Agent indicates it didn't understand or timed out (e.g., "Je n'ai rien entendu...", `[ASR_SILENCE_TIMEOUT]`, `[ASR_UNKNOWN_VALUE]`) and offers to retry or switch mode.
*   **TC-GEN-6: Clean Exit**:
    *   Steps: Press `Ctrl+C` or type `quitter` (if implemented as an exit command).
    *   Expected: Agent exits cleanly (e.g., "Au revoir!").

### TC-ENV: Environment & Configuration
*   **TC-ENV-1: Missing Critical Keys in `.env`**:
    *   Steps: Temporarily remove or corrupt `GEMINI_API_KEY` in `.env`. Start `agent.py` or `main.py`.
    *   Expected: Agent/API fails to start or initialize services, logging clear errors about the missing key. `GeminiClient` should raise `ValueError`. Health check should show Gemini error.
*   **TC-ENV-2: Missing Service-Specific Key (e.g., `DATABASE_URL`)**:
    *   Steps: Remove `DATABASE_URL` from `.env`. Start agent/API. Attempt an action requiring DB access (e.g., get contract details).
    *   Expected: The specific action fails gracefully, logging errors. Health check shows DB error. Agent might respond with a technical issue message.

### TC-FS: Fail-Safe Mechanisms (Clarification & Handoff)
(Run `python src/agent.py`)
*   **TC-FS-1: Trigger Clarification**:
    *   Steps: Ask an ambiguous question (e.g., "Je veux des infos sur l'assurance.").
    *   Expected: Agent responds starting with `[CLARIFY]` and asks a clarifying question (e.g., "Quel type d'assurance vous intéresse?"). Provide clarification. Agent uses it for the next response.
*   **TC-FS-2: Trigger Handoff (After Clarification Fails)**:
    *   Steps: To a clarification question, give another vague or unhelpful answer.
    *   Expected: Agent eventually responds starting with `[HANDOFF]` and suggests contacting a human advisor.
*   **TC-FS-3: Trigger Handoff (User Request / Complex Query)**:
    *   Steps: Ask "Je veux parler à un conseiller." or a very complex, out-of-scope question.
    *   Expected: Agent responds with `[HANDOFF]`.

### TC-DB: Database Interactions (via Gemini Function Calling)
(Run `python src/agent.py`. Requires database schema initialized and potentially sample data.)
*   **TC-DB-1: Get Contract Details (Exists)**:
    *   Steps: "Donne-moi les détails de mon contrat numéro XYZ." (Use an existing `numero_contrat` from your sample data).
    *   Expected: Agent uses `get_contrat_details` function. Gemini formulates a response summarizing the contract type, status, adherent, formula, and key guarantees with their terms.
*   **TC-DB-2: Get Contract Details (Does Not Exist)**:
    *   Steps: "Je voudrais les infos pour la police ABC999." (Use a non-existent `numero_contrat`).
    *   Expected: Agent uses `get_contrat_details`. Gemini responds that the contract was not found or asks to verify the number.
*   **TC-DB-3: Open Claim (Success)**:
    *   Steps: "Je veux déclarer un sinistre pour mon contrat XYZ. C'est un dégât des eaux dans ma cuisine. C'est arrivé hier." (Provide `numero_contrat`, `type_sinistre`, `description_sinistre`, optional `date_survenance`).
    *   Expected: Agent uses `open_claim` function. A new record is created in `sinistres_artex`. Gemini confirms the claim declaration has been recorded by Artex and provides the internal reference ID (`id_sinistre_artex`).
*   **TC-DB-4: Open Claim (Contract Not Found)**:
    *   Steps: Attempt to open a claim for a non-existent `numero_contrat`.
    *   Expected: Agent uses `open_claim`. Gemini responds that the contract number is invalid or not found.

### TC-TTS: Text-to-Speech Service
(Primarily observed via `agent.py` voice output and logs from `tts.py` if run standalone)
*   **TC-TTS-1: Google Cloud TTS (if configured)**:
    *   Steps: Ensure `GOOGLE_APPLICATION_CREDENTIALS` and `TTS_USE_GOOGLE_CLOUD=true` are correctly set in `.env`. Interact with `agent.py`.
    *   Expected: Voice output should be of higher quality (Google Cloud). Logs in `tts.py` (if testing standalone) should indicate Google Cloud TTS usage. Check `TTS_CACHE_DIR` for MP3s.
*   **TC-TTS-2: gTTS Fallback**:
    *   Steps: Unset `GOOGLE_APPLICATION_CREDENTIALS` or set `TTS_USE_GOOGLE_CLOUD=false`. Interact with `agent.py`.
    *   Expected: Voice output uses gTTS. Logs indicate fallback. Check `TTS_CACHE_DIR`.
*   **TC-TTS-3: Caching**:
    *   Steps: Ask the agent to say the same phrase multiple times.
    *   Expected: First time, TTS is generated. Subsequent times, logs should indicate a cache hit, and response should be faster. Verify MP3 file in `TTS_CACHE_DIR`.

### TC-LK: LiveKit PoC Mode
(Run `python src/agent.py --livekit-room testroom --livekit-identity artexbot` for these tests. Requires LiveKit server.)
*   **TC-LK-1: Connect to LiveKit Room**:
    *   Steps: Run agent in LiveKit mode.
    *   Expected: Logs indicate `LiveKitParticipantHandler` attempting to connect, (simulated) join success, and (simulated) welcome message played via TTS publishing path.
*   **TC-LK-2: Simulated TTS in LiveKit Mode**:
    *   Steps: Agent needs to generate a response (e.g., after a simulated user query via CLI text).
    *   Expected: Logs from `LiveKitParticipantHandler` show "Would publish TTS audio..." or similar, indicating TTS output is routed to the LiveKit publishing logic (which is currently simulated). No local audio playback via Pygame.
*   **TC-LK-3: Simulated ASR & Full Interaction in LiveKit Mode**:
    *   Steps: When agent is "listening" in LiveKit mode, it will prompt for text input ("Simulated LiveKit STT Input:"). Type a query.
    *   Expected: Logs from `LiveKitParticipantHandler` show (simulated) `TrackPublished` event for a remote user, then (simulated) ASR processing of dummy audio, then ideally the typed text being used as the "transcribed" input for Gemini. Agent responds using simulated TTS publishing.
*   **TC-LK-4: Silence Hangup in LiveKit Mode**:
    *   Steps: Connect to LiveKit. Play welcome message. Wait for `USER_SILENCE_HANGUP_SECONDS` (e.g., 30s) without providing any (simulated text) input.
    *   Expected: `LiveKitParticipantHandler` logs user silence timeout and initiates disconnect. Agent exits or signals disconnection.
*   **TC-LK-5: Clean Exit from LiveKit Mode**:
    *   Steps: Press `Ctrl+C` while agent is in LiveKit mode.
    *   Expected: Agent logs disconnection from LiveKit and exits cleanly.

### TC-API: FastAPI Application
(Run `uvicorn src.main:app --host 0.0.0.0 --port 8000`. Requires services like DB, Gemini to be configured in `.env`.)
*   **TC-API-1: Root Endpoint**:
    *   Steps: Open `http://localhost:8000/` in a browser or use `curl`.
    *   Expected: JSON response `{"message": "Welcome to the ARTEX Assurances AI Agent API"}`.
*   **TC-API-2: Health Check (All OK)**:
    *   Steps: Ensure DB and Gemini (`GEMINI_API_KEY`) are correctly configured. Access `http://localhost:8000/healthz`.
    *   Expected: JSON response with `overall_status: "ok"`, and `database_status: "ok"`, `gemini_status: "ok"`.
*   **TC-API-3: Health Check (DB Error)**:
    *   Steps: Stop MySQL server or corrupt `DATABASE_URL`. Access `http://localhost:8000/healthz`.
    *   Expected: JSON response with `overall_status: "error"`, `database_status: "error"` (or "not_configured"), `gemini_status: "ok"`.
*   **TC-API-4: Health Check (Gemini Error)**:
    *   Steps: Remove/corrupt `GEMINI_API_KEY`. Restart API. Access `http://localhost:8000/healthz`.
    *   Expected: JSON response with `overall_status: "error"`, `gemini_status: "error_api_key_missing"` (or similar).
*   **TC-API-5: LiveKit Webhook Placeholder**:
    *   Steps: Send a POST request with any JSON payload to `http://localhost:8000/webhook/livekit` (e.g., using `curl` or Postman).
        ```bash
        # curl -X POST -H "Content-Type: application/json" -d '{"event":"test_event", "data":"some_data"}' http://localhost:8000/webhook/livekit
        ```
    *   Expected: JSON response `{"status": "webhook_received_successfully"}`. Check API logs for the printed payload.
*   **TC-API-6: CORS Headers**:
    *   Steps: From a different origin (e.g., a simple HTML page served on a different port, or using Postman/curl with an `Origin` header like `http://localhost:3001`), make a GET request to `/`.
    *   Expected: Response includes CORS headers like `access-control-allow-origin`. (Exact check depends on client, but presence of header is key).

## 4. Notes and Known Limitations
*   **LiveKit gRPC Client**: The current LiveKit participant logic in `livekit_participant_handler.py` uses placeholder gRPC stubs. Actual audio streaming to/from LiveKit requires generating these stubs from LiveKit's `.proto` files and fully implementing the RTC client logic. The current tests simulate these interactions.
*   **FFmpeg/LibAV**: `pydub` requires FFmpeg or LibAV for MP3 processing. Ensure it's installed on the system where the agent runs.
*   **Google Cloud Credentials**: For Google Cloud TTS, `GOOGLE_APPLICATION_CREDENTIALS` must point to a valid service account key JSON file with the Text-to-Speech API enabled.
*   **Sample Data**: Some database tests require pre-existing sample data that aligns with the schema.
