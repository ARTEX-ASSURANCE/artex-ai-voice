# Manual Testing Guide for ARTEX ASSURANCES AI Agent

This guide provides steps for manually testing the ARTEX ASSURANCES AI Agent.

## Setup

1.  **Install Dependencies**:
    *   Ensure you have Python 3.10+ installed.
    *   Open a terminal in the `artex_agent` root directory.
    *   Install required Python packages:
        ```bash
        pip install -r requirements.txt
        ```
    *   **System Dependencies**: The agent uses PyAudio, Pygame, which might require system-level libraries.
        *   For Debian/Ubuntu:
            ```bash
            sudo apt-get update
            sudo apt-get install -y portaudio19-dev python3-pyaudio libsdl2-mixer-2.0-0
            ```
        *   For other OS, please refer to PyAudio and Pygame installation guides if you encounter issues.

2.  **Set Environment Variable**:
    *   The agent requires the `GEMINI_API_KEY` for accessing Google's Generative AI. Set this environment variable in your terminal session or system-wide.
        ```bash
        export GEMINI_API_KEY="YOUR_API_KEY_HERE"
        ```
        Replace `"YOUR_API_KEY_HERE"` with your actual Gemini API key.

3.  **Run the Agent**:
    *   Navigate to the `artex_agent` root directory in your terminal.
    *   Execute the agent script:
        ```bash
        python src/agent.py
        ```

## Test Cases

### TC1: French Voice Input and Output

*   **Steps**:
    1.  Start the agent as described in Setup.
    2.  When the agent prints "Parlez maintenant...", say a simple phrase in French (e.g., "Bonjour, comment ça va?").
*   **Expected**:
    1.  The agent should print "Transcription en cours..."
    2.  It should then print your transcribed phrase, e.g., "Vous (voix): Bonjour, comment ça va?"
    3.  The agent should print "Agent (ARTEX): ...pense...".
    4.  The agent should print its textual response from Gemini, e.g., "Agent (ARTEX) (texte): Bonjour ! Je vais bien, merci de demander. Comment puis-je vous aider aujourd'hui ?"
    5.  The agent should then speak this response in French using Text-to-Speech.

### TC2: ARTEX Persona and Context

*   **Steps**:
    1.  Start the agent.
    2.  Use voice or text input to ask a question related to insurance (e.g., "Qu'est-ce qu'une assurance habitation?" or "Parle-moi de l'assurance auto.").
*   **Expected**:
    1.  The agent responds in French.
    2.  The tone should be professional, helpful, and consistent with an insurance assistant for ARTEX ASSURANCES.
    3.  The response content should be relevant to the insurance question.
    4.  The agent should offer to direct you to a human agent for complex queries it cannot handle, as per its context prompt.

### TC3: Input Mode Switching (Voice to Text)

*   **Steps**:
    1.  Start the agent (it defaults to voice input).
    2.  When "Parlez maintenant..." is displayed, wait for a few seconds without speaking, or mumble.
    3.  The agent should prompt: "Agent (ARTEX): Problème avec la reconnaissance vocale. Taper 'texte' pour saisie manuelle, ou appuyez sur Entrée pour réessayer la voix:"
    4.  Type `texte` and press Enter.
*   **Expected**:
    1.  The agent should print "Agent (ARTEX): Mode de saisie par texte activé."
    2.  The input prompt should change to "Vous (texte): ".

### TC4: Input Mode Switching (Text to Voice)

*   **Steps**:
    1.  Ensure the agent is in text input mode (follow TC3).
    2.  At the "Vous (texte): " prompt, type `voix` and press Enter.
*   **Expected**:
    1.  The agent should print "Agent (ARTEX): Mode de saisie vocale activé."
    2.  The agent should prompt "Parlez maintenant...".

### TC5: Handling Unclear Audio

*   **Steps**:
    1.  Start the agent.
    2.  When "Parlez maintenant..." is displayed, mumble incoherently or make a very short, non-speech sound.
*   **Expected**:
    1.  The agent should print a message like "Agent (ARTEX): Désolé, je n'ai pas compris ce que vous avez dit. Veuillez réessayer ou taper votre requête."
    2.  It should then prompt again to switch mode or retry voice: "Agent (ARTEX): Problème avec la reconnaissance vocale. Taper 'texte' pour saisie manuelle, ou appuyez sur Entrée pour réessayer la voix:"

### TC6: API Error (Simulated if possible, otherwise conceptual)

*   **Steps**: This is difficult to force reliably. One way to simulate is to temporarily set an invalid `GEMINI_API_KEY` before starting the agent, or disconnect from the internet after starting.
    *   If `GEMINI_API_KEY` is invalid, the error "ValueError: GEMINI_API_KEY environment variable not set..." or an API error during `configure_gemini()` or `generate_response()` should appear.
    *   If internet is disconnected during a `generate_response()` call.
*   **Expected**:
    *   If `configure_gemini()` fails due to API key, it should print "Erreur de configuration: ..." and exit or not proceed to main loop.
    *   If `generate_response()` fails, it should print a message like "Agent (ARTEX): Error generating response from API: ..." or "Error: Could not get a response from the model." and then attempt to speak this error message. The agent should continue running to allow further interaction attempts or mode switching.

### TC7: Exit

*   **Steps**:
    1.  Start the agent.
    2.  Press `Ctrl+C` in the terminal.
*   **Expected**:
    1.  The agent should print "\nAu revoir!" (if `KeyboardInterrupt` is caught).
    2.  It should then print "Application terminée." as part of the `finally` block.
    3.  The agent should exit cleanly.

## Notes

*   **Hardware**: A working microphone is required for voice input, and speakers/headphones are needed for voice output.
*   **Gemini Variability**: Responses from the Gemini model can vary even for the same prompt. Focus on the relevance, tone, and language rather than an exact word-for-word match with expected outputs.
*   **Network**: An active internet connection is required for Google Speech Recognition and Google Gemini API calls.
*   **Environment**: Ensure no other application is heavily using the microphone or audio output, which might interfere.
