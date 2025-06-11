# ARTEX ASSURANCES AI Agent

## Description

A voice-enabled AI assistant for ARTEX ASSURANCES, capable of conversing in French. It uses Google's Gemini API for advanced language understanding and generation, and provides voice input/output capabilities through local machine hardware or a simulated interaction in a LiveKit room. This agent is designed to assist users with queries related to ARTEX ASSURANCES' products and services, including fetching policy details and updating user preferences via database integration.

## Features

*   **Converses in French**: All interactions, including voice input and output, are in French.
*   **Powered by Google Gemini API**: Utilizes the `gemini-pro` model for natural language processing.
*   **Voice Input (Standard Mode)**: Employs Speech-to-Text (`SpeechRecognition` library) for spoken French.
*   **Voice Output (Standard Mode)**: Uses Text-to-Speech (`gTTS` and `pygame`) to vocalize responses in French.
*   **Contextual & Persona-Driven Responses**: Agent is primed with a system context to act as a professional and helpful ARTEX ASSURANCES assistant.
*   **Interactive Command-Line Interface**: Allows users to interact via voice or text, with options to switch modes.
*   **.env File Based Configuration**: Securely manages API keys and service URLs.
*   **MySQL Database Integration**:
    *   Retrieves policy details (e.g., coverage, dates, premium).
    *   Updates user preferences (e.g., communication opt-ins).
*   **Enhanced Fail-Safe Mechanisms**:
    *   Agent requests clarification (`[CLARIFY]` tag) for ambiguous queries.
    *   Can perform a simulated human handoff (`[HANDOFF]` tag) for complex situations or user requests.
*   **Proof-of-Concept (PoC) LiveKit Integration**:
    *   Agent can join a LiveKit room as a participant.
    *   Simulated audio I/O: TTS is logged, and STT is via text input when in LiveKit mode.

## Setup and Installation

1.  **Clone the Repository (if applicable)**:
    ```bash
    # git clone <repository_url>
    # cd artex_agent
    ```

2.  **Python Dependencies**:
    Install all required Python packages using `pip` and the `requirements.txt` file:
    ```bash
    pip install -r requirements.txt
    ```
    This includes libraries like `google-generativeai`, `SpeechRecognition`, `PyAudio`, `gTTS`, `pygame`, `pytest`, `python-dotenv`, `aiomysql`, `SQLAlchemy`, and `livekit`.

3.  **System Dependencies**:
    Certain Python packages (especially `PyAudio` and `pygame`) require system-level libraries. For Debian/Ubuntu-based systems, install them using:
    ```bash
    sudo apt-get update
    sudo apt-get install -y portaudio19-dev python3-pyaudio libsdl2-mixer-2.0-0
    ```
    For other operating systems, refer to the installation documentation for PyAudio and Pygame.

4.  **`.env` File Configuration**:
    Create a file named `.env` in the root of the `artex_agent` project directory. This file stores sensitive credentials and service URLs. Add the following content, replacing placeholders with your actual values:
    ```env
    GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
    DATABASE_URL="mysql+aiomysql://YOUR_DB_USER:YOUR_DB_PASSWORD@YOUR_DB_HOST:YOUR_DB_PORT/YOUR_DB_NAME"
    LIVEKIT_URL="wss://YOUR_LIVEKIT_SERVER_URL"
    LIVEKIT_API_KEY="YOUR_LIVEKIT_API_KEY"
    LIVEKIT_API_SECRET="YOUR_LIVEKIT_API_SECRET"
    ```
    *   `GEMINI_API_KEY`: Your API key for Google Gemini.
    *   `DATABASE_URL`: Connection string for your MySQL database (e.g., `mysql+aiomysql://user:pass@host:3306/mydb`).
    *   `LIVEKIT_URL`: URL of your LiveKit server (e.g., `wss://my-livekit-instance.livekit.cloud`).
    *   `LIVEKIT_API_KEY` & `LIVEKIT_API_SECRET`: Credentials for the LiveKit Server API.
    The `.env` file is listed in `.gitignore` and should not be committed to version control.

5.  **MySQL Database Setup**:
    A running MySQL server (version 8 or compatible) is required for features involving database interaction.
    *   The connection string is specified via the `DATABASE_URL` in the `.env` file.
    *   The agent assumes a database schema that includes tables like `policies` and `user_preferences`. For hypothetical examples of these schemas, see the comments in `src/database.py`.
    *   You will need to create these tables and populate them with relevant sample data for the database functionalities to work correctly during testing.

6.  **LiveKit Server Setup**:
    For using the LiveKit Proof-of-Concept features, you need access to a running LiveKit server.
    *   The server URL and API credentials must be configured in the `.env` file as described above.

## How to Run

Navigate to the project's root directory (`artex_agent`).

*   **Standard Mode (CLI with local Voice/Text I/O)**:
    ```bash
    python src/agent.py
    ```

*   **LiveKit Mode (PoC with simulated Voice/Text I/O over LiveKit)**:
    ```bash
    python src/agent.py --livekit-room YOUR_ROOM_NAME --livekit-identity YOUR_AGENT_IDENTITY
    ```
    *   Replace `YOUR_ROOM_NAME` with the name of the LiveKit room you want the agent to join (e.g., `artex_support_room`).
    *   Replace `YOUR_AGENT_IDENTITY` with a unique identity for the agent participant (e.g., `artex_support_agent`). The default identity is `artex_agent_poc`.

## Usage

*   Upon starting, the agent will greet you in French.
*   **Standard Mode**:
    *   It defaults to voice input. When "Parlez maintenant..." is displayed, speak clearly in French.
    *   If voice input fails or you prefer text, type `texte` when prompted to switch to text input mode ("Vous (texte):").
    *   To switch back to voice from text mode, type `voix`.
*   **LiveKit Mode (PoC)**:
    *   The agent joins the specified LiveKit room.
    *   Voice input (STT) is simulated via text input in the console: "Agent (LiveKit - Simulant STT): Entrez le texte de l'utilisateur:".
    *   Voice output (TTS) is simulated by logging the text to the console: "Agent (LiveKit TTS - Sim): [response]".
*   **General Interactions**:
    *   You can ask for information about insurance products, request details about a specific policy by providing its ID (e.g., "Donne-moi les détails de la police POL123"), or ask to update your communication preferences (e.g., "Je ne veux plus recevoir d'e-mails pour l'utilisateur USER001").
    *   The agent may ask for clarification (`[CLARIFY]`) or suggest a handoff to a human agent (`[HANDOFF]`) if needed.
*   **Exiting**: Type `exit` or `quit`, or press `Ctrl+C`.

## Testing

*   **Manual Testing**: A comprehensive guide for manual testing of all features (standard mode, LiveKit PoC, database interactions, fail-safe mechanisms) is available in `TESTING_GUIDE.md`.
*   **Automated Tests**: The project is set up with `pytest`. Any automated unit or integration tests (currently, `tests/test_agent.py` has a placeholder) can be run using:
    ```bash
    pytest
    ```

## Project Structure

*   `artex_agent/`: Root directory of the project.
    *   `src/`: Contains the main source code.
        *   `agent.py`: Core application logic, CLI, interaction handling, Gemini API calls, STT/TTS.
        *   `database.py`: Handles MySQL database connections and operations (CRUD operations for policies, preferences).
        *   `livekit_integration.py`: Manages LiveKit service connection, room joining, and simulated audio I/O for the PoC.
    *   `tests/`: Contains automated tests.
        *   `test_agent.py`: Placeholder for future automated tests.
    *   `.env`: Local environment configuration file (stores API keys, DB URLs - **not committed to Git**).
    *   `requirements.txt`: Lists all Python dependencies for the project.
    *   `README.md`: This file – provides an overview, setup, usage, and testing information.
    *   `TESTING_GUIDE.md`: Detailed manual testing instructions.
    *   `.gitignore`: Specifies intentionally untracked files that Git should ignore.

## Future Development Ideas
*   Full audio streaming in LiveKit mode (integrate actual STT from LiveKit participant audio and TTS to a LiveKit audio track).
*   More sophisticated conversation history management.
*   Expanded database operations and NLP understanding for more complex queries.
*   Integration with other CRM or communication platforms.
*   More robust error handling and logging.
