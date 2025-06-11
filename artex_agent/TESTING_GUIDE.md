# Manual Testing Guide for ARTEX ASSURANCES AI Agent

This guide provides steps for manually testing the ARTEX ASSURANCES AI Agent, covering its various functionalities including voice interaction, database operations, and LiveKit integration (Proof of Concept).

## 1. Setup and Configuration

### 1.1. Install Dependencies
*   Ensure you have Python 3.10+ installed.
*   Open a terminal in the `artex_agent` root directory.
*   Install required Python packages:
    ```bash
    pip install -r requirements.txt
    ```
*   **System Dependencies**: The agent uses PyAudio and Pygame for local voice I/O, which might require system-level libraries.
    *   For Debian/Ubuntu:
        ```bash
        sudo apt-get update
        sudo apt-get install -y portaudio19-dev python3-pyaudio libsdl2-mixer-2.0-0
        ```
    *   For other OS, please refer to PyAudio and Pygame installation guides if you encounter issues.

### 1.2. Environment Variables (`.env` file)
*   The agent relies on an `.env` file in the `artex_agent` root directory to manage API keys and service URLs.
*   Create a file named `.env` by copying from `.env.template` (`cp .env.template .env`) and populate it with the following keys:
    ```env
    GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
    DATABASE_URL="mysql+aiomysql://YOUR_DB_USER:YOUR_DB_PASSWORD@YOUR_DB_HOST:YOUR_DB_PORT/YOUR_DB_NAME"
    LIVEKIT_URL="wss://YOUR_LIVEKIT_SERVER_URL"
    LIVEKIT_API_KEY="YOUR_LIVEKIT_API_KEY"
    LIVEKIT_API_SECRET="YOUR_LIVEKIT_API_SECRET"
    ```
    *   Replace placeholder values (e.g., `YOUR_GEMINI_API_KEY`) with your actual credentials and service details.
    *   The `.gitignore` file is configured to prevent committing the `.env` file.

### 1.3. Database Setup (for Database Interaction Tests)
*   For test cases involving database interactions (TC-DB series), ensure you have a MySQL database server running and accessible.
*   The database schema should align with the models defined in `src/database_models.py` (tables: `clients`, `contrats`, `remboursements`, `sinistres`, `user_preferences`).
*   You can initialize the schema using the `init_db.py` script:
    ```bash
    python artex_agent/init_db.py
    ```
    Set `DROP_TABLES_FIRST=true` as an environment variable if you want to drop existing tables before creation.
*   Populate tables with sample data (e.g., policy `POL123`, user `USER001` in `user_preferences`, a client `USER001` in `clients`) for the tests to pass as described.

### 1.4. LiveKit Server Setup (for LiveKit PoC Tests)
*   For LiveKit integration tests (TC-LK series), ensure you have a LiveKit server instance running and accessible.
*   The `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` in your `.env` file must point to this server.

## 2. Running the Agent

*   Navigate to the `artex_agent` root directory in your terminal.
*   **Standard Mode (CLI Voice/Text)**:
    ```bash
    python src/agent.py
    ```
*   **LiveKit Mode (PoC)**:
    ```bash
    python src/agent.py --livekit-room YOUR_ROOM_NAME --livekit-identity YOUR_AGENT_IDENTITY
    ```
    *   Replace `YOUR_ROOM_NAME` with a desired room name (e.g., `artex_test_room`).
    *   Replace `YOUR_AGENT_IDENTITY` with a unique identity for the agent in the room (e.g., `artex_voice_agent`). The default is `artex_agent_poc`.

## 3. General Interaction Test Cases

### TC-GEN-1: Basic French Voice Interaction (Standard Mode)
*   **Mode**: Standard
*   **Steps**:
    1.  Start the agent: `python src/agent.py`.
    2.  When prompted "Parlez maintenant...", say a simple French phrase (e.g., "Bonjour, comment ça va?").
*   **Expected**:
    1.  Agent transcribes speech ("Vous (voix): ...").
    2.  Agent indicates it's thinking ("Agent (ARTEX): ...pense...").
    3.  Agent prints its textual response ("Agent (ARTEX) (texte): ...").
    4.  Agent speaks the response in French using local TTS (pygame).

### TC-GEN-2: ARTEX Persona and Contextual Response
*   **Mode**: Standard or LiveKit
*   **Steps**: Ask an insurance-related question (e.g., "Qu'est-ce qu'une assurance habitation?" or "Parle-moi de l'assurance auto.").
*   **Expected**: Agent responds in French, professionally, consistent with ARTEX persona, and provides relevant information.

### TC-GEN-3: Input Mode Switching (Voice to Text - Standard Mode)
*   **Mode**: Standard
*   **Steps**:
    1.  Start agent. At "Parlez maintenant...", wait or mumble.
    2.  Agent prompts to switch: "...Taper 'texte' pour saisie manuelle...". Type `texte`.
*   **Expected**: Agent switches to text input ("Agent (ARTEX): Mode de saisie par texte activé."). Prompt changes to "Vous (texte):".

### TC-GEN-4: Input Mode Switching (Text to Voice - Standard Mode)
*   **Mode**: Standard
*   **Steps**: In text mode, type `voix`.
*   **Expected**: Agent switches to voice input ("Agent (ARTEX): Mode de saisie vocale activé."). Prompt changes to "Parlez maintenant...".

### TC-GEN-5: Handling Unclear Audio (Standard Mode)
*   **Mode**: Standard
*   **Steps**: Mumble or stay silent at "Parlez maintenant...".
*   **Expected**: Agent indicates non-comprehension ("Agent (ARTEX): Désolé, je n'ai pas compris...") and prompts to retry/switch.

### TC-GEN-6: Clean Exit
*   **Mode**: Standard or LiveKit
*   **Steps**: Press `Ctrl+C` in the terminal where the agent is running.
*   **Expected**: Agent prints "Au revoir!", "Application terminée.", and exits cleanly. If in LiveKit mode, LiveKit cleanup messages should also appear.

## 4. Environment Variable and Configuration Tests

### TC-ENV-1: Missing Critical Keys in `.env`
*   **Steps**:
    1.  Temporarily rename or remove the `.env` file, OR remove/comment out `GEMINI_API_KEY`.
    2.  Try to start the agent: `python src/agent.py`.
*   **Expected**: Agent fails to start or initialize critical services (Gemini), printing an error message (e.g., "ValueError: GEMINI_API_KEY environment variable not set..."). The application might exit or critical functionalities will be impaired.

### TC-ENV-2: Missing Service-Specific Key (e.g., `DATABASE_URL`)
*   **Steps**:
    1.  Ensure `.env` exists with `GEMINI_API_KEY`.
    2.  Remove or comment out `DATABASE_URL` from `.env`.
    3.  Start the agent.
    4.  Ask a question that would trigger a database operation (e.g., "Donne-moi les détails de la police POL123").
*   **Expected**:
    1.  Agent starts, Gemini initializes.
    2.  Database engine initialization fails (logged to console: "CRITICAL: DATABASE_URL environment variable not set..." or similar from `src/database.py`).
    3.  When a DB operation is attempted, Gemini should be prompted to inform the user of a configuration problem (e.g., "Désolé, je ne peux pas accéder à la base de données pour le moment en raison d'un problème de configuration.").

## 5. Database Interaction Test Cases (Requires DB Setup as per 1.3)

### TC-DB-1: Read Policy Details (Policy Exists)
*   **Mode**: Standard or LiveKit
*   **Prerequisites**: Database contains a policy, e.g., `policy_id="POL123"`, `user_id="USER001"`, `policy_type="Auto"`, `start_date="2023-01-01"`, `end_date="2024-01-01"`, `premium_amount=500.00`, `status="Actif"`.
*   **Steps**: Ask "Quels sont les détails de ma police POL123?".
*   **Expected**: Agent responds with the details of policy POL123, formulated in natural language by Gemini (e.g., "Votre police auto POL123 est active du 2023-01-01 au 2024-01-01 avec une prime de 500.00.").

### TC-DB-2: Read Policy Details (Policy Does Not Exist)
*   **Mode**: Standard or LiveKit
*   **Steps**: Ask "Quels sont les détails de ma police POLXYZ?".
*   **Expected**: Agent states that policy POLXYZ was not found and may ask if you want to try another ID (e.g., "Je n'ai pas trouvé de police avec le numéro POLXYZ. Souhaitez-vous vérifier le numéro ou essayer autre chose?").

### TC-DB-3: Update User Preference (Success - Set to True)
*   **Mode**: Standard or LiveKit
*   **Prerequisites**: A user preference record for `user_id="USER001"` can be created/updated.
*   **Steps**: Ask "Je voudrais recevoir les mises à jour par e-mail pour l'utilisateur USER001." (Gemini should request JSON with `receive_updates: true`).
*   **Expected**: Agent confirms the preference has been updated to true (e.g., "Parfait, l'utilisateur USER001 recevra désormais les mises à jour par e-mail.").

### TC-DB-4: Update User Preference (Success - Set to False)
*   **Mode**: Standard or LiveKit
*   **Prerequisites**: A user preference record for `user_id="USER001"`.
*   **Steps**: Ask "Je ne veux plus recevoir les mises à jour par e-mail pour USER001." (Gemini should request JSON with `receive_updates: false`).
*   **Expected**: Agent confirms the preference has been updated to false (e.g., "Compris, l'utilisateur USER001 ne recevra plus les mises à jour par e-mail.").

### TC-DB-5: Database Operation Error (Conceptual)
*   **Steps**: If the database becomes unavailable (e.g., MySQL server is stopped) while the agent is running, and a query requiring DB access is made.
*   **Expected**: Agent informs the user of a technical problem trying to access the database and suggests trying later (e.g., "Je rencontre un problème technique pour accéder aux informations. Veuillez réessayer plus tard.").

## 6. Fail-Safe Mechanism Tests (Clarification & Handoff)

### TC-FS-1: Trigger Clarification
*   **Mode**: Standard or LiveKit
*   **Steps**: Ask an ambiguous question like "Parle-moi de l'assurance."
*   **Expected**: Agent's response starts with `[CLARIFY]` and asks for more specific details (e.g., "Agent (ARTEX) a besoin de précisions: Pourriez-vous préciser quel type d'assurance vous intéresse?"). Provide a clarification. Agent uses it for the next response.

### TC-FS-2: Trigger Handoff (After Clarification Fails)
*   **Mode**: Standard or LiveKit
*   **Steps**:
    1.  Trigger a clarification (TC-FS-1).
    2.  When asked for clarification, give another vague or unhelpful response that leads Gemini to still be unable to answer.
*   **Expected**: Agent recognizes it still cannot help and initiates a handoff (e.g., "Même avec ces précisions, il serait préférable de parler à un conseiller pour cette situation. Je vous mets en relation." or similar, possibly after a second `[CLARIFY]` leading to handoff logic).

### TC-FS-3: Trigger Handoff (Directly by Gemini or Explicit User Request)
*   **Mode**: Standard or LiveKit
*   **Steps**: Ask a question that is explicitly outside the agent's scope as defined in `ARTEX_CONTEXT_PROMPT` (e.g., "Je veux acheter des actions ARTEX") or directly say "Je veux parler à un conseiller."
*   **Expected**: Agent responds with a handoff message (e.g., "Je comprends. Pour vous aider au mieux, je vais vous mettre en relation avec un conseiller humain."). The conversation might end or prompt for further, unrelated queries.

## 7. LiveKit PoC Test Cases (Requires LiveKit Setup as per 1.4)

### TC-LK-1: Connect to LiveKit Room
*   **Mode**: LiveKit
*   **Steps**: Run agent with `--livekit-room my_test_room --livekit-identity agent_artie_01`.
*   **Expected**:
    1.  Console logs indicate: "LiveKit RoomServiceClient initialized...", "Token generated...", "Connecting to room my_test_room...", "Successfully joined LiveKit room: my_test_room as agent_artie_01".
    2.  Agent prints: "Agent en mode LiveKit. Saisie vocale simulée par entrée texte."
    3.  Input prompt changes to "Agent (LiveKit - Simulant STT): Entrez le texte de l'utilisateur:".
    4.  `handle_room_events` task starts (indicated by "Setting up event handlers...").

### TC-LK-2: Simulated TTS in LiveKit Mode
*   **Mode**: LiveKit
*   **Steps**: After connecting (TC-LK-1), type a query like "Bonjour".
*   **Expected**:
    1.  Agent processes query with Gemini.
    2.  Console logs: "Agent (LiveKit TTS - Sim): [Response Text from Gemini]".
    3.  Textual response also printed: "Agent (ARTEX) (texte): [Response Text from Gemini]".
    4.  No local audio playback via pygame.

### TC-LK-3: Simulated STT & Full Interaction in LiveKit Mode
*   **Mode**: LiveKit
*   **Steps**: Continue interaction by typing various queries. Test a database query (e.g., "détails police POL123") and a clarification scenario.
*   **Expected**:
    1.  Agent uses text input as simulated STT.
    2.  All interaction flows (DB queries, clarification, handoff) work as in standard mode, but with TTS simulated via console logs.
    3.  Agent remains connected to LiveKit. (External verification: check LiveKit server dashboard or another client to see the agent participant).

### TC-LK-4: Exit from LiveKit Mode
*   **Mode**: LiveKit
*   **Steps**: Type `exit` or press `Ctrl+C`.
*   **Expected**: Agent logs "Au revoir!", LiveKit cleanup messages ("Closing LiveKit service client...", "LiveKit room disconnected...", "LiveKit event handler task cancelled."), "Application terminée.", and exits cleanly.

## 8. Notes and Known Limitations

*   **Hardware (Standard Mode)**: A working microphone and speakers are needed for voice I/O in standard mode.
*   **Gemini Variability**: LLM responses can vary. Focus on relevance, tone, and adherence to instructions (like JSON format, `[CLARIFY]`/`[HANDOFF]` tags) rather than exact phrasing.
*   **Network**: Active internet is required for Google services (Gemini, Speech Recognition) and LiveKit.
*   **LiveKit PoC**:
    *   Audio streaming (both publishing agent's TTS and receiving participant's STT) is **simulated**.
    *   TTS is logged to the console; it's not actually sent as audio frames to the LiveKit room.
    *   STT uses text input from the console, not actual audio from other LiveKit participants.
*   **Database**: Assumes schema in `src/database_models.py` exists and is populated for tests requiring data. The `init_db.py` script can create the schema.
*   **Error Handling**: While error handling for common issues (API keys, DB connection) is present, it may not cover all edge cases.
