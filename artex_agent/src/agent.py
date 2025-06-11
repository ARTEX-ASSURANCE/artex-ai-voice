import google.generativeai as genai
import os
import speech_recognition as sr
from gtts import gTTS
import pygame
import tempfile
import time

# Global variable to store the initialized model
model = None
_pygame_mixer_initialized = False

ARTEX_CONTEXT_PROMPT = """Tu es un assistant virtuel pour ARTEX ASSURANCES.
Tu es là pour aider les clients avec leurs questions sur les produits d'assurance (auto, habitation, santé, prévoyance, etc.) et les services associés.
Réponds toujours en français, de manière professionnelle, courtoise et amicale.
Fournis des informations claires et concises. Si une question est trop complexe ou sort de ton domaine de compétence, suggère poliment de contacter un conseiller ARTEX ASSURANCES.
Ne donne pas de conseils financiers spécifiques, mais explique les caractéristiques des produits.
Sois patient et empathique.
"""

def configure_gemini():
    """
    Configures the Gemini API key from the environment variable GEMINI_API_KEY.

    Raises:
        ValueError: If the GEMINI_API_KEY environment variable is not set.
    """
    global model
    if model is None: # Configure only if not already configured
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set. Please set it before running the agent.")
        genai.configure(api_key=api_key)
        # Initialize the model here to be reused
        try:
            # For gemini-pro, system_instruction is a parameter for starting a chat or specific generation calls.
            # We will prepend it to the prompt in generate_response for stateless calls.
            # If we were using model.start_chat(), we could pass it there.
            model = genai.GenerativeModel('gemini-pro')
        except Exception as e:
            print(f"Error initializing the GenerativeModel: {e}")
            raise

def generate_response(prompt: str) -> str:
    """
    Generates a response from the Gemini model.

    Args:
        prompt: The user's input prompt.

    Returns:
        The model's text response.
    """
    global model
    if model is None:
        # This ensures configuration is called if generate_response is called directly
        # or if the initial configuration in main failed silently (though it shouldn't with current error handling)
        print("Model not configured. Attempting to configure...")
        configure_gemini()
        if model is None: # If it's still None after trying to configure, something is wrong.
             return "Error: Model could not be initialized. Please check API key and configuration."

    # Combine context, French instruction, and user prompt
    # The "Assistant:" part helps guide the model to start its response.
    full_prompt = f"{ARTEX_CONTEXT_PROMPT}\n---\nRéponds en français à la question suivante :\nUtilisateur: {prompt}\nAssistant:"

    try:
        # It's good practice to log the full prompt for debugging if issues occur
        # print(f"DEBUG: Full prompt sent to Gemini:\n{full_prompt}")
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        print(f"Error generating response from API: {e}")
        return "Error: Could not get a response from the model."

def listen_and_transcribe_french() -> str | None:
    """
    Listens for audio input via microphone and transcribes it to French text.

    Returns:
        The transcribed text as a string, or None if recognition fails.
    """
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("Parlez maintenant...")
        try:
            # Adjust for ambient noise for 1 second
            r.adjust_for_ambient_noise(source, duration=1)
            # Listen for audio input
            audio = r.listen(source, timeout=5, phrase_time_limit=10) # Added timeout and phrase_time_limit
            print("Transcription en cours...")
            # Recognize speech using Google Web Speech API
            text = r.recognize_google(audio, language='fr-FR')
            print(f"Vous (voix): {text}")
            return text
        except sr.WaitTimeoutError:
            print("Agent (ARTEX): Aucun son détecté. Veuillez réessayer ou taper votre requête.")
            return None
        except sr.UnknownValueError:
            print("Agent (ARTEX): Désolé, je n'ai pas compris ce que vous avez dit. Veuillez réessayer ou taper votre requête.")
            return None
        except sr.RequestError as e:
            print(f"Agent (ARTEX): Erreur de service de reconnaissance vocale; {e}. Veuillez vérifier votre connexion ou taper votre requête.")
            return None
        except Exception as e:
            print(f"Agent (ARTEX): Une erreur est survenue lors de la reconnaissance vocale: {e}. Veuillez réessayer ou taper votre requête.")
            return None

def speak_french(text: str):
    """
    Converts text to speech in French and plays it.
    Ensures pygame.mixer is initialized.
    """
    global _pygame_mixer_initialized
    if not _pygame_mixer_initialized:
        try:
            pygame.mixer.init()
            _pygame_mixer_initialized = True
        except pygame.error as e:
            print(f"Agent (ARTEX): Erreur lors de l'initialisation de pygame.mixer: {e}. La parole ne sera pas jouée.")
            return

    if not text:
        print("Agent (ARTEX): Pas de texte à vocaliser.")
        return

    try:
        tts = gTTS(text=text, lang='fr', slow=False)
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=True) as tmpfile:
            temp_filename = tmpfile.name
            tts.save(temp_filename)
            # Ensure file is written before loading and playing
            # For gTTS, save() is blocking, so this should be fine.

            pygame.mixer.music.load(temp_filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
        # File is automatically deleted here when delete=True
        # No need to explicitly unload or delete if using with delete=True and it works.
        # If issues arise, might need delete=False and manual cleanup.

    except RuntimeError as re: # Specific error gTTS might throw for no text
        print(f"Agent (ARTEX): Erreur gTTS (RuntimeError): {re}. Assurez-vous qu'il y a du texte à dire.")
    except Exception as e:
        print(f"Agent (ARTEX): Erreur lors de la génération ou de la lecture de la parole: {e}")

if __name__ == "__main__":
    # print("ARTEX ASSURANCES AI Agent") # Original title
    # print("=========================") # Original separator
    print("Bonjour! Je suis l'assistant IA d'ARTEX ASSURANCES. Comment puis-je vous aider?")
    print("==================================================================================")

    global _pygame_mixer_initialized # Allow main to modify this
    try:
        # Initialize pygame mixer here once
        try:
            pygame.mixer.init()
            _pygame_mixer_initialized = True
            print("Audio mixer initialisé.") # For debugging
        except pygame.error as e:
            print(f"Agent (ARTEX): Attention - Erreur lors de l'initialisation de pygame.mixer: {e}. Les réponses vocales pourraient ne pas fonctionner.")
            _pygame_mixer_initialized = False # Explicitly set to False

        configure_gemini()
        # print("Gemini API configured successfully.") # Keep this internal or remove for cleaner UI
        print("Dites quelque chose (ou tapez 'texte' pour saisie manuelle, 'exit'/'quit' pour terminer).")
        print("Vous pouvez aussi taper 'texte' pour passer en mode saisie manuelle.")

        input_mode = "voice" # Start with voice input

        while True:
            user_input = None
            if input_mode == "voice":
                transcribed_text = listen_and_transcribe_french()
                if transcribed_text:
                    user_input = transcribed_text
                else:
                    # Offer to switch to text input if voice fails
                    choice = input("Agent (ARTEX): Problème avec la reconnaissance vocale. Taper 'texte' pour saisie manuelle, ou appuyez sur Entrée pour réessayer la voix: ").lower()
                    if choice == 'texte':
                        input_mode = "text"
                        print("Agent (ARTEX): Mode de saisie par texte activé.")
                        continue # Restart loop to get text input
                    else:
                        continue # Retry voice input

            if input_mode == "text":
                user_input = input("Vous (texte): ")
                if user_input.lower() == 'voix': # Allow switching back to voice
                    input_mode = "voice"
                    print("Agent (ARTEX): Mode de saisie vocale activé.")
                    continue

            if user_input: # Process if we have input (either voice or text)
                if user_input.lower() in ['exit', 'quit']:
                    print("Au revoir!")
                    break
                if not user_input.strip(): # Should primarily apply to text input now
                    print("Agent (ARTEX): Veuillez entrer une demande valide.")
                    continue

                print("Agent (ARTEX): ...pense...") # Thinking indicator
                agent_response = generate_response(user_input)
                print(f"Agent (ARTEX) (texte): {agent_response}") # Log response to console
                speak_french(agent_response) # Speak the response

            # If voice input failed and user didn't switch to text, user_input might be None.
            # The loop continues, and listen_and_transcribe_french() will be called again.
            # If text input is active and user just presses enter, user_input will be empty string.

            except EOFError: # Handle Ctrl+D
                print("\nAu revoir!")
                break
    except ValueError as ve:
        print(f"Erreur de configuration: {ve}")
    except KeyboardInterrupt:
        print("\nAu revoir!")
    except Exception as e:
        print(f"Une erreur inattendue est survenue: {e}")
    finally:
        if _pygame_mixer_initialized:
            pygame.mixer.quit()
        pygame.quit() # Quit pygame itself
        print("Application terminée.")
