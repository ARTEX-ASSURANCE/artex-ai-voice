# ARTEX ASSURANCES AI Agent

## Description

A voice-enabled AI assistant for ARTEX ASSURANCES, capable of conversing in French, using Google's Gemini for language understanding and generation, and providing voice input/output. This agent is designed to assist users with queries related to ARTEX ASSURANCES' products and services.

## Features

*   **Converses in French**: All interactions, including voice input and output, are in French.
*   **Powered by Google Gemini API**: Utilizes the `gemini-pro` model for advanced language understanding and response generation.
*   **Voice Input**: Employs Speech-to-Text technology (`SpeechRecognition` library) to understand spoken French.
*   **Voice Output**: Uses Text-to-Speech technology (`gTTS` and `pygame`) to vocalize responses in French.
*   **Contextual Responses**: The agent is primed with a system context to act as an assistant for ARTEX ASSURANCES, understanding its role and providing relevant information about insurance products (e.g., auto, home, health).
*   **Interactive Command-Line Interface**: Allows users to interact via voice or text, with options to switch between modes.

## Setup and Installation

1.  **Clone the Repository (if applicable)**:
    ```bash
    # git clone <repository_url>
    # cd artex_agent
    ```

2.  **Python Dependencies**:
    Install the required Python packages using `pip`:
    ```bash
    pip install -r requirements.txt
    ```

3.  **System Dependencies**:
    Certain Python packages (like PyAudio and Pygame) require system-level libraries. For Debian/Ubuntu-based systems, install them using:
    ```bash
    sudo apt-get update
    sudo apt-get install -y portaudio19-dev python3-pyaudio libsdl2-mixer-2.0-0
    ```
    For other operating systems, please refer to the installation documentation for PyAudio and Pygame. More details can also be found in the `TESTING_GUIDE.md`.

4.  **Set Gemini API Key**:
    You need a Google Gemini API key. Set it as an environment variable:
    ```bash
    export GEMINI_API_KEY="YOUR_API_KEY_HERE"
    ```
    Replace `"YOUR_API_KEY_HERE"` with your actual API key. This can be added to your shell profile (e.g., `.bashrc`, `.zshrc`) for persistence.

## How to Run

Navigate to the project's root directory (`artex_agent`) and run the agent script:

```bash
python src/agent.py
```

## Usage

*   The agent will greet you in French.
*   By default, it expects **voice input**. When you see "Parlez maintenant...", speak clearly in French.
*   If voice input fails or you prefer text, you can type `texte` when prompted to switch to text input mode. The prompt will change to "Vous (texte):".
*   To switch back to voice input from text mode, type `voix`.
*   To exit the agent, type `exit` or `quit`, or press `Ctrl+C`.

## Testing

*   **Manual Testing**: Detailed instructions for manual testing, including various scenarios, are available in `TESTING_GUIDE.md`. This includes testing voice input/output, persona consistency, mode switching, and error handling.
*   **Automated Tests**: The project is set up with `pytest`. If automated unit or integration tests are added, they can be run using:
    ```bash
    pytest
    ```
    Currently, `tests/test_agent.py` contains a placeholder test.

## Project Structure

*   `src/agent.py`: Contains the main application logic for the AI agent, including interaction handling, API calls, speech-to-text, and text-to-speech.
*   `requirements.txt`: Lists all Python dependencies required for the project.
*   `TESTING_GUIDE.md`: Provides detailed instructions for manual testing of the agent.
*   `.gitignore`: Specifies intentionally untracked files that Git should ignore (e.g., `__pycache__/`, environment files).
*   `tests/`: Directory intended for automated tests.
    *   `test_agent.py`: Placeholder for automated tests.
*   `README.md`: This file – provides an overview of the project.
