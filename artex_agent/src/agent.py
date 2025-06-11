import os
import google.generativeai as genai
from dotenv import load_dotenv
import speech_recognition as sr
from gtts import gTTS
import pygame
import tempfile
import time
import json
import asyncio
import src.database as database
import src.livekit_integration as livekit_integration # Import LiveKit module
import argparse # For command-line arguments

# Load environment variables from .env file
load_dotenv()

ARTEX_CONTEXT_PROMPT = """Tu es un assistant virtuel pour ARTEX ASSURANCES.
Tu es là pour aider les clients avec leurs questions sur les produits d'assurance (auto, habitation, santé, prévoyance, etc.) et les services associés.
Réponds toujours en français, de manière professionnelle, courtoise et amicale.
Fournis des informations claires et concises. Si une question est trop complexe ou sort de ton domaine de compétence, suggère poliment de contacter un conseiller ARTEX ASSURANCES.
Ne donne pas de conseils financiers spécifiques, mais explique les caractéristiques des produits.
Sois patient et empathique.
Si tu n'es pas sûr de la réponse ou si la question de l'utilisateur est ambiguë, inclus la phrase '[CLARIFY]' au début de ta réponse, suivie de la question de clarification que tu souhaites poser à l'utilisateur. Par exemple: '[CLARIFY] Pourriez-vous préciser quel type d'assurance vous intéresse?'
Si, même après une clarification, tu ne peux pas aider l'utilisateur ou si la situation est trop complexe ou sort de ton domaine d'expertise, inclus la phrase '[HANDOFF]' au début de ta réponse. Tu peux aussi suggérer un transfert si l'utilisateur le demande explicitement (par exemple, s'il dit "je veux parler à un humain").

Instructions pour les opérations de base de données (Réponds uniquement avec le JSON si une telle action est demandée par l'utilisateur et que tu as les informations nécessaires, comme les IDs):
Pour obtenir des détails sur une police, si l'utilisateur fournit un numéro de police, réponds avec un JSON: `{"action": "db_read", "operation": "get_policy_details", "params": {"policy_id": "ID_DE_LA_POLICE"}}`. Demande d'abord le numéro de police si non fourni.
Pour mettre à jour les préférences e-mail d'un utilisateur (par exemple, s'il veut s'inscrire ou se désinscrire des mises à jour), réponds avec: `{"action": "db_edit", "operation": "update_user_preference", "params": {"user_id": "ID_UTILISATEUR", "receive_updates": true_ou_false}}`. Demande d'abord l'ID utilisateur si non fourni.
"""

# Global database engine instance
db_engine = None

# Global LiveKit instances
livekit_room_service_client = None
livekit_room_instance = None # Stores the connected Room object
livekit_event_handler_task = None # Stores the asyncio task for LiveKit events


def configure_gemini():
    """
    Configures the Gemini API key from the environment variable GEMINI_API_KEY.

    Raises:
        ValueError: If the GEMINI_API_KEY environment variable is not set.
    """
    global model, db_engine, livekit_room_service_client # Add livekit client
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

    # Initialize database engine if not already done
    if db_engine is None:
        try:
            db_engine = database.get_db_engine()
            # Test DB connection once at startup (optional, can be noisy)
            # print("Testing DB connection on startup...")
            # test_success, test_msg = asyncio.run(database.test_database_connection(db_engine))
            # print(f"DB startup test: {test_success} - {test_msg}")
            print("Database engine initialized successfully in configure_gemini.")
        except Exception as e:
            print(f"Failed to initialize database engine in configure_gemini: {e}")
            # db_engine will remain None, subsequent DB operations should fail gracefully

    if livekit_room_service_client is None:
        try:
            livekit_room_service_client = livekit_integration.get_livekit_room_service()
            print("LiveKit RoomServiceClient initialized successfully in configure_gemini.")
        except Exception as e:
            print(f"Failed to initialize LiveKit RoomServiceClient in configure_gemini: {e}")


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
    global _pygame_mixer_initialized, livekit_room_instance

    if livekit_room_instance:
        print(f"Agent (LiveKit TTS - Sim): {text}")
        # For PoC, directly call the async function using asyncio.run() from the sync context.
        # This is a simplification. In a full async app, you'd await it.
        try:
            asyncio.run(livekit_integration.publish_tts_audio_to_room(livekit_room_instance, text))
        except Exception as e:
            print(f"Error during simulated LiveKit TTS publish: {e}")
        return # Skip pygame playback if in LiveKit mode

    # Fallback to pygame if not in LiveKit mode or if livekit_room_instance is None
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
            pygame.mixer.music.load(temp_filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
    except RuntimeError as re:
        print(f"Agent (ARTEX): Erreur gTTS (RuntimeError): {re}. Assurez-vous qu'il y a du texte à dire.")
    except Exception as e:
        print(f"Agent (ARTEX): Erreur lors de la génération ou de la lecture de la parole: {e}")


async def main_async_logic(args):
    """Main asynchronous logic for the agent, especially when LiveKit is involved."""
    global livekit_room_instance, livekit_event_handler_task, input_mode

    if args.livekit_room:
        if not livekit_room_service_client:
            print("LiveKit service client not initialized. Cannot join room.")
            return # Or raise an error

        livekit_room_instance = await livekit_integration.join_room_and_publish_audio(
            livekit_room_service_client,
            args.livekit_room,
            args.livekit_identity
        )
        if livekit_room_instance:
            print(f"Successfully joined LiveKit room: {args.livekit_room}")
            # Start the event handler as a background task
            livekit_event_handler_task = asyncio.create_task(
                livekit_integration.handle_room_events(livekit_room_instance)
            )
            input_mode = "text" # Default to text input when in LiveKit mode for PoC
            print("Agent en mode LiveKit. Saisie vocale simulée par entrée texte.")
        else:
            print(f"Could not join LiveKit room: {args.livekit_room}. Falling back to CLI mode.")
            # Fallback or exit, depending on desired behavior

    # The main conversation loop (adapted for async if other parts become async)
    # For now, the loop itself remains synchronous and uses asyncio.run for async parts.
    # This is a PoC simplification. A fully async app would structure this differently.

    # The existing main loop logic will run here.
    # If livekit_room_instance is set, listen_and_transcribe_french and speak_french will behave differently.
    # For this PoC, the loop from the original `if __name__ == "__main__":` will be mostly reused,
    # with modifications inside listen_and_transcribe_french and speak_french.

    # The loop needs to be here or called from here if main functions are to be async.
    # Due to pygame and input() being sync, a fully async loop is complex.
    # We'll keep the existing loop structure and adapt I/O functions.
    run_cli_conversation_loop()


def run_cli_conversation_loop():
    global input_mode # Allow this function to modify the global input_mode

    # This is the original main loop, refactored into a function
    # It will be called by main_async_logic or directly by if __name__ == "__main__"
    # if LiveKit is not used.

    print("Dites quelque chose (ou tapez 'texte' pour saisie manuelle, 'exit'/'quit' pour terminer).")
    if not livekit_room_instance: # Only show this if not in LiveKit mode, where text is default for PoC
        print("Vous pouvez aussi taper 'texte' pour passer en mode saisie manuelle.")


    while True:
        user_input = None
        if livekit_room_instance:
            # In LiveKit mode, PoC simulates STT via text input
            print("Agent (LiveKit - Simulant STT): Entrez le texte de l'utilisateur:")
            user_input = input(f"Vous ({args.livekit_identity_cli_prompt if args.livekit_room else 'texte'}): ")
            if user_input.lower() == 'voix': # Not applicable in LiveKit PoC mode
                print("Agent (ARTEX): Le mode vocal direct est remplacé par la simulation LiveKit.")
                user_input = "" # Clear to avoid processing 'voix' as query
        elif input_mode == "voice":
            transcribed_text = listen_and_transcribe_french()
            # ... (rest of the voice input logic from original main)
            if transcribed_text:
                user_input = transcribed_text
            else:
                choice = input("Agent (ARTEX): Problème avec la reconnaissance vocale. Taper 'texte' pour saisie manuelle, ou appuyez sur Entrée pour réessayer la voix: ").lower()
                if choice == 'texte':
                    input_mode = "text"
                    print("Agent (ARTEX): Mode de saisie par texte activé.")
                    continue
                else:
                    continue

        if input_mode == "text" and not livekit_room_instance : # Standard text input if not LiveKit
            user_input = input("Vous (texte): ")
            if user_input.lower() == 'voix':
                input_mode = "voice"
                print("Agent (ARTEX): Mode de saisie vocale activé.")
                continue

        # ... (The rest of the extensive main loop logic from the previous version) ...
        # This includes:
        #   - if user_input:
        #   -   if user_input.lower() in ['exit', 'quit']: ... break
        #   -   if not user_input.strip(): ... continue
        #   -   original_user_query = user_input
        #   -   agent_response_text = generate_response(original_user_query)
        #   -   JSON parsing for DB actions
        #   -   HANDOFF/CLARIFY checks
        #   -   speak_french(final_response)
        # This entire block needs to be here. For brevity in diff, it's not repeated.
        # Ensure this logic is correctly placed within run_cli_conversation_loop.
        # For this PoC, I will paste the relevant part of the loop here.

        if user_input:
            if user_input.lower() in ['exit', 'quit']:
                print("Au revoir!")
                break
            if not user_input.strip():
                print("Agent (ARTEX): Veuillez entrer une demande valide.")
                continue

            original_user_query = user_input
            print("Agent (ARTEX): ...pense...")
            agent_response_text = generate_response(original_user_query)

            try:
                if agent_response_text.strip().startswith("```json"):
                    cleaned_response_text = agent_response_text.strip().replace("```json", "").replace("```", "").strip()
                    parsed_action = json.loads(cleaned_response_text)
                elif agent_response_text.strip().startswith("{"):
                    parsed_action = json.loads(agent_response_text)
                else:
                    parsed_action = None
            except json.JSONDecodeError:
                parsed_action = None

            if parsed_action and "action" in parsed_action:
                action_type = parsed_action.get("action")
                operation = parsed_action.get("operation")
                params = parsed_action.get("params", {})
                final_agent_response_for_user = ""

                if not db_engine:
                    error_message = "Désolé, je ne peux pas accéder à la base de données pour le moment en raison d'un problème de configuration."
                    print(f"Agent (ARTEX) (erreur): {error_message}")
                    speak_french(error_message)
                    continue

                if action_type == "db_read" and operation == "get_policy_details":
                    policy_id = params.get("policy_id")
                    if policy_id:
                        print(f"Agent (ARTEX): Recherche des détails de la police {policy_id}...")
                        try:
                            policy_data = asyncio.run(database.get_policy_details(db_engine, policy_id))
                            if policy_data:
                                db_result_prompt = f"L'utilisateur a demandé des informations sur sa police '{policy_id}'. Les données de la base de données sont: {json.dumps(policy_data)}. Formule une réponse concise et informative en français pour l'utilisateur, présentant ces détails de manière claire."
                            else:
                                db_result_prompt = f"L'utilisateur a demandé des détails pour la police ID '{policy_id}', mais aucune police correspondante n'a été trouvée dans la base de données. Informe l'utilisateur de cela en français et demande s'il souhaite essayer un autre ID ou obtenir de l'aide pour autre chose."
                        except Exception as db_e:
                            print(f"Erreur lors de l'accès à la base de données pour get_policy_details (policy_id: {policy_id}): {db_e}")
                            db_result_prompt = f"Une erreur s'est produite lors de la tentative de récupération des détails de la police ID '{policy_id}'. Informe l'utilisateur en français qu'il y a eu un problème technique et suggère de réessayer plus tard ou de contacter le support si le problème persiste."
                        final_agent_response_for_user = generate_response(db_result_prompt)
                    else:
                        final_agent_response_for_user = "Je n'ai pas reçu de numéro de police à rechercher. Pourriez-vous me le fournir s'il vous plaît?"

                elif action_type == "db_edit" and operation == "update_user_preference":
                    user_id = params.get("user_id")
                    receive_updates = params.get("receive_updates")
                    if user_id is not None and isinstance(receive_updates, bool):
                        print(f"Agent (ARTEX): Mise à jour des préférences pour l'utilisateur {user_id} à {receive_updates}...")
                        try:
                            success = asyncio.run(database.update_user_preference(db_engine, user_id, receive_updates))
                            if success:
                                db_result_prompt = f"La préférence de l'utilisateur '{user_id}' pour recevoir des mises à jour par e-mail (receive_updates) a été mise à jour avec succès à la valeur '{receive_updates}'. Confirme cela à l'utilisateur en français de manière claire et positive."
                            else:
                                db_result_prompt = f"La tentative de mise à jour des préférences e-mail pour l'utilisateur '{user_id}' à la valeur '{receive_updates}' n'a pas pu être confirmée (il se peut que l'utilisateur n'existe pas ou que la préférence était déjà cette valeur). Informe l'utilisateur et demande s'il veut vérifier l'ID utilisateur."
                        except Exception as db_e:
                            print(f"Erreur lors de l'accès à la base de données pour update_user_preference (user_id: {user_id}): {db_e}")
                            db_result_prompt = f"La tentative de mise à jour des préférences e-mail pour l'utilisateur '{user_id}' a échoué en raison d'un problème technique. Informe l'utilisateur de cet échec en français et suggère de réessayer plus tard."
                        final_agent_response_for_user = generate_response(db_result_prompt)
                    else:
                        final_agent_response_for_user = "Les informations fournies pour la mise à jour des préférences sont incomplètes ou incorrectes. J'ai besoin d'un ID utilisateur valide et d'un choix clair (oui ou non) pour les mises à jour par e-mail."
                else:
                    final_agent_response_for_user = "J'ai reçu une instruction pour interagir avec la base de données que je ne reconnais pas. Pourriez-vous reformuler votre demande?"

                if final_agent_response_for_user.startswith("[HANDOFF]"):
                    handoff_msg = final_agent_response_for_user.replace("[HANDOFF]", "").strip() or "Il semble que j'aie besoin de transférer votre demande à un conseiller."
                    print(f"Agent (ARTEX): {handoff_msg}")
                    speak_french(handoff_msg)
                    print("Conversation terminée après tentative d'opération DB.")
                    break
                elif final_agent_response_for_user.startswith("[CLARIFY]"):
                    clarify_msg = final_agent_response_for_user.replace("[CLARIFY]", "").strip()
                    handoff_msg = f"Agent (ARTEX): Pour mieux vous aider avec cela, il serait préférable de parler à un conseiller. {clarify_msg}"
                    print(handoff_msg)
                    speak_french(handoff_msg)
                    print("Conversation terminée, clarification requise après opération DB.")
                    break
                else:
                    print(f"Agent (ARTEX) (texte): {final_agent_response_for_user}")
                    speak_french(final_agent_response_for_user)
                continue

            agent_response = agent_response_text
            if agent_response.startswith("[HANDOFF]"):
                handoff_message_from_gemini = agent_response.replace("[HANDOFF]", "").strip()
                if handoff_message_from_gemini:
                    full_handoff_message = f"Agent (ARTEX): {handoff_message_from_gemini} Je vais vous mettre en relation avec un conseiller humain. Veuillez patienter."
                else:
                    full_handoff_message = "Agent (ARTEX): Je comprends. Pour vous aider au mieux, je vais vous mettre en relation avec un conseiller humain. Veuillez patienter un instant."
                print(full_handoff_message)
                speak_french(full_handoff_message)
                print("Conversation terminée après proposition de transfert.")
                break

            elif agent_response.startswith("[CLARIFY]"):
                clarification_question = agent_response.replace("[CLARIFY]", "").strip()
                clarification_message = f"Agent (ARTEX) a besoin de précisions: {clarification_question}"
                print(clarification_message)
                speak_french(clarification_question)

                user_clarification = None
                current_input_mode_for_clarification = input_mode # Preserve current mode for clarification
                if livekit_room_instance: # If in LiveKit mode, clarification uses text input
                     print("Agent (LiveKit - Simulant STT pour clarification): Entrez votre précision:")
                     user_clarification = input(f"Vous ({args.livekit_identity_cli_prompt if args.livekit_room else 'texte'} - précision): ")
                elif current_input_mode_for_clarification == "voice":
                    print("Veuillez fournir votre précision oralement:")
                    user_clarification = listen_and_transcribe_french()
                    while not user_clarification:
                        retry_choice = input("Agent (ARTEX): Problème avec la reconnaissance de votre précision. Taper 'texte' pour saisie manuelle, ou appuyez sur Entrée pour réessayer la voix: ").lower()
                        if retry_choice == 'texte':
                            current_input_mode_for_clarification = "text"
                            print("Agent (ARTEX): Mode de saisie par texte activé pour la précision.")
                            break
                        print("Veuillez réessayer votre précision oralement:")
                        user_clarification = listen_and_transcribe_french()

                if current_input_mode_for_clarification == "text" and not user_clarification: # Handles text mode or switch during voice
                     user_clarification = input(f"Vous (précision texte): ")

                if user_clarification:
                    new_prompt_for_gemini = (
                        f"La question originale de l'utilisateur était : \"{original_user_query}\". "
                        f"L'assistant (IA) a demandé une précision : \"{clarification_question}\". "
                        f"L'utilisateur a répondu avec la précision suivante : \"{user_clarification}\". "
                        "Maintenant, réponds de manière complète à la question originale en tenant compte de cette précision. "
                        "Si tu ne peux toujours pas répondre ou si c'est trop complexe, utilise [HANDOFF]."
                    )
                    print("Agent (ARTEX): ...pense (avec précision)...")
                    agent_response_after_clarification = generate_response(new_prompt_for_gemini)

                    if agent_response_after_clarification.startswith("[HANDOFF]"):
                        handoff_message_from_gemini = agent_response_after_clarification.replace("[HANDOFF]", "").strip()
                        if handoff_message_from_gemini:
                            full_handoff_message = f"Agent (ARTEX): {handoff_message_from_gemini} Il semble que j'aie encore besoin d'aide pour répondre. Je vous mets en relation avec un conseiller."
                        else:
                            full_handoff_message = "Agent (ARTEX): Même avec ces précisions, il serait préférable de parler à un conseiller pour cette situation. Je vous mets en relation."
                        print(full_handoff_message)
                        speak_french(full_handoff_message)
                        print("Conversation terminée après tentative de clarification infructueuse.")
                        break
                    elif agent_response_after_clarification.startswith("[CLARIFY]"):
                        handoff_message = "Agent (ARTEX): J'ai encore besoin de précisions, et pour éviter de vous faire répéter, il serait peut-être mieux de parler directement à un conseiller. Je vous mets en relation."
                        print(handoff_message)
                        speak_french(handoff_message)
                        print("Conversation terminée après clarifications multiples.")
                        break
                    else:
                        print(f"Agent (ARTEX) (texte): {agent_response_after_clarification}")
                        speak_french(agent_response_after_clarification)
                else:
                    no_clarification_message = "Agent (ARTEX): Pas de précision fournie. Veuillez reposer votre question ou demander à parler à un conseiller si vous êtes bloqué."
                    print(no_clarification_message)
                    speak_french(no_clarification_message)
            else:
                print(f"Agent (ARTEX) (texte): {agent_response}")
                speak_french(agent_response)

        # ... (rest of the loop, if any, or it ends here for one interaction) ...
        # except EOFError, ValueError, KeyboardInterrupt, Exception as before

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ARTEX ASSURANCES AI Agent")
    parser.add_argument("--livekit-room", type=str, help="Name of the LiveKit room to join.")
    parser.add_argument("--livekit-identity", type=str, default="artex_agent_poc", help="Participant identity for LiveKit.")
    parser.add_argument("--livekit-identity-cli-prompt", type=str, default="LiveKit User", help="Prompt name for CLI input when in LiveKit mode.") # For PoC
    args = parser.parse_args()

    print("Bonjour! Je suis l'assistant IA d'ARTEX ASSURANCES. Comment puis-je vous aider?")
    print("Bonjour! Je suis l'assistant IA d'ARTEX ASSURANCES. Comment puis-je vous aider?")
    print("==================================================================================")

    global _pygame_mixer_initialized # Allow main to modify this

    # load_dotenv() # Called at the top of the script now

    try:
        # Initialize pygame mixer here once
        try:
            pygame.mixer.init()
            _pygame_mixer_initialized = True
            print("Audio mixer initialisé.") # For debugging
        except pygame.error as e:
            print(f"Agent (ARTEX): Attention - Erreur lors de l'initialisation de pygame.mixer: {e}. Les réponses vocales pourraient ne pas fonctionner.")
            _pygame_mixer_initialized = False # Explicitly set to False

        # Attempt to configure Gemini, which now relies on os.getenv after load_dotenv
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

                original_user_query = user_input # Store the original query

                print("Agent (ARTEX): ...pense...")
                agent_response_text = generate_response(original_user_query)

                # Attempt to parse as JSON for DB operations
                try:
                    # Gemini might sometimes wrap JSON in ```json ... ```, so try to strip that
                    if agent_response_text.strip().startswith("```json"):
                        cleaned_response_text = agent_response_text.strip()
                        cleaned_response_text = cleaned_response_text.replace("```json", "").replace("```", "").strip()
                        parsed_action = json.loads(cleaned_response_text)
                    elif agent_response_text.strip().startswith("{"): # Check if it looks like JSON
                        parsed_action = json.loads(agent_response_text)
                    else:
                        parsed_action = None
                except json.JSONDecodeError:
                    parsed_action = None # Not a JSON command

                if parsed_action and "action" in parsed_action:
                    action_type = parsed_action.get("action")
                    operation = parsed_action.get("operation")
                    params = parsed_action.get("params", {})

                    final_agent_response_for_user = "" # This will hold the text Gemini generates after DB op

                    if not db_engine:
                        error_message = "Désolé, je ne peux pas accéder à la base de données pour le moment en raison d'un problème de configuration."
                        print(f"Agent (ARTEX) (erreur): {error_message}")
                        speak_french(error_message)
                        continue # Go to next iteration of the loop

                    # Handle DB Read Action
                    if action_type == "db_read" and operation == "get_policy_details":
                        policy_id = params.get("policy_id")
                        if policy_id:
                            print(f"Agent (ARTEX): Recherche des détails de la police {policy_id}...")
                            try:
                                policy_data = asyncio.run(database.get_policy_details(db_engine, policy_id))
                                if policy_data: # Data found
                                    db_result_prompt = f"L'utilisateur a demandé des informations sur sa police '{policy_id}'. Les données de la base de données sont: {json.dumps(policy_data)}. Formule une réponse concise et informative en français pour l'utilisateur, présentant ces détails de manière claire."
                                else: # Data not found
                                    db_result_prompt = f"L'utilisateur a demandé des détails pour la police ID '{policy_id}', mais aucune police correspondante n'a été trouvée dans la base de données. Informe l'utilisateur de cela en français et demande s'il souhaite essayer un autre ID ou obtenir de l'aide pour autre chose."
                            except Exception as db_e: # Database error
                                print(f"Erreur lors de l'accès à la base de données pour get_policy_details (policy_id: {policy_id}): {db_e}")
                                db_result_prompt = f"Une erreur s'est produite lors de la tentative de récupération des détails de la police ID '{policy_id}'. Informe l'utilisateur en français qu'il y a eu un problème technique et suggère de réessayer plus tard ou de contacter le support si le problème persiste."
                            final_agent_response_for_user = generate_response(db_result_prompt)
                        else: # policy_id was not provided in params
                            final_agent_response_for_user = "Je n'ai pas reçu de numéro de police à rechercher. Pourriez-vous me le fournir s'il vous plaît?"

                    # Handle DB Edit Action
                    elif action_type == "db_edit" and operation == "update_user_preference":
                        user_id = params.get("user_id")
                        receive_updates = params.get("receive_updates")
                        if user_id is not None and isinstance(receive_updates, bool):
                            print(f"Agent (ARTEX): Mise à jour des préférences pour l'utilisateur {user_id} à {receive_updates}...")
                            try:
                                success = asyncio.run(database.update_user_preference(db_engine, user_id, receive_updates))
                                if success:
                                    db_result_prompt = f"La préférence de l'utilisateur '{user_id}' pour recevoir des mises à jour par e-mail (receive_updates) a été mise à jour avec succès à la valeur '{receive_updates}'. Confirme cela à l'utilisateur en français de manière claire et positive."
                                else:
                                    # This 'else' might be hit if rowcount is 0, meaning user_id not found or value was already set to the new value.
                                    # The database function itself doesn't distinguish these cases for a simple True/False return.
                                    # For a more nuanced response, database.py would need to return more specific info.
                                    db_result_prompt = f"La tentative de mise à jour des préférences e-mail pour l'utilisateur '{user_id}' à la valeur '{receive_updates}' n'a pas pu être confirmée (il se peut que l'utilisateur n'existe pas ou que la préférence était déjà cette valeur). Informe l'utilisateur et demande s'il veut vérifier l'ID utilisateur."
                            except Exception as db_e: # Technical error during DB operation
                                print(f"Erreur lors de l'accès à la base de données pour update_user_preference (user_id: {user_id}): {db_e}")
                                db_result_prompt = f"La tentative de mise à jour des préférences e-mail pour l'utilisateur '{user_id}' a échoué en raison d'un problème technique. Informe l'utilisateur de cet échec en français et suggère de réessayer plus tard."
                            final_agent_response_for_user = generate_response(db_result_prompt)
                        else: # user_id or receive_updates missing/invalid
                            final_agent_response_for_user = "Les informations fournies pour la mise à jour des préférences sont incomplètes ou incorrectes. J'ai besoin d'un ID utilisateur valide et d'un choix clair (oui ou non) pour les mises à jour par e-mail."

                    else: # Unknown DB action or operation
                        final_agent_response_for_user = "J'ai reçu une instruction pour interagir avec la base de données que je ne reconnais pas. Pourriez-vous reformuler votre demande?"

                    # Output the final response to the user
                    # Check for HANDOFF/CLARIFY in this secondary response as well.
                    if final_agent_response_for_user.startswith("[HANDOFF]"):
                        handoff_msg = final_agent_response_for_user.replace("[HANDOFF]", "").strip() or "Il semble que j'aie besoin de transférer votre demande à un conseiller."
                        print(f"Agent (ARTEX): {handoff_msg}")
                        speak_french(handoff_msg)
                        print("Conversation terminée après tentative d'opération DB.")
                        break
                    elif final_agent_response_for_user.startswith("[CLARIFY]"):
                         # Simplified: if DB action leads to new clarify, treat as handoff for now to avoid complex loop
                        clarify_msg = final_agent_response_for_user.replace("[CLARIFY]", "").strip()
                        handoff_msg = f"Agent (ARTEX): Pour mieux vous aider avec cela, il serait préférable de parler à un conseiller. {clarify_msg}"
                        print(handoff_msg)
                        speak_french(handoff_msg)
                        print("Conversation terminée, clarification requise après opération DB.")
                        break
                    else:
                        print(f"Agent (ARTEX) (texte): {final_agent_response_for_user}")
                        speak_french(final_agent_response_for_user)
                    continue # End current turn and wait for new user input

                # If not a DB action, proceed with CLARIFY/HANDOFF/normal response logic using original agent_response_text
                agent_response = agent_response_text

                if agent_response.startswith("[HANDOFF]"):
                    handoff_message_from_gemini = agent_response.replace("[HANDOFF]", "").strip()
                    if handoff_message_from_gemini:
                        full_handoff_message = f"Agent (ARTEX): {handoff_message_from_gemini} Je vais vous mettre en relation avec un conseiller humain. Veuillez patienter."
                    else:
                        full_handoff_message = "Agent (ARTEX): Je comprends. Pour vous aider au mieux, je vais vous mettre en relation avec un conseiller humain. Veuillez patienter un instant."
                    print(full_handoff_message)
                    speak_french(full_handoff_message)
                    # For now, we will end the conversation after handoff.
                    # Future: Implement actual handoff mechanism (e.g., LiveKit call)
                    print("Conversation terminée après proposition de transfert.")
                    break # Exit the loop

                elif agent_response.startswith("[CLARIFY]"):
                    clarification_question = agent_response.replace("[CLARIFY]", "").strip()
                    clarification_message = f"Agent (ARTEX) a besoin de précisions: {clarification_question}"
                    print(clarification_message)
                    speak_french(clarification_question) # Speak only the question part

                    # Get user's clarification
                    user_clarification = None
                    if input_mode == "voice":
                        print("Veuillez fournir votre précision oralement:")
                        user_clarification = listen_and_transcribe_french()
                        while not user_clarification: # Loop until valid clarification or switch mode
                            retry_choice = input("Agent (ARTEX): Problème avec la reconnaissance de votre précision. Taper 'texte' pour saisie manuelle, ou appuyez sur Entrée pour réessayer la voix: ").lower()
                            if retry_choice == 'texte':
                                input_mode = "text" # Switch mode for clarification
                                print("Agent (ARTEX): Mode de saisie par texte activé pour la précision.")
                                break
                            print("Veuillez réessayer votre précision oralement:")
                            user_clarification = listen_and_transcribe_french()

                    if input_mode == "text": # Handles initial text mode or switch during voice clarification
                        if not user_clarification: # if switched from voice and still no input
                             user_clarification = input(f"Vous (précision texte): ")


                    if user_clarification:
                        new_prompt_for_gemini = (
                            f"La question originale de l'utilisateur était : \"{original_user_query}\". "
                            f"L'assistant (IA) a demandé une précision : \"{clarification_question}\". "
                            f"L'utilisateur a répondu avec la précision suivante : \"{user_clarification}\". "
                            "Maintenant, réponds de manière complète à la question originale en tenant compte de cette précision. "
                            "Si tu ne peux toujours pas répondre ou si c'est trop complexe, utilise [HANDOFF]."
                        )
                        print("Agent (ARTEX): ...pense (avec précision)...")
                        agent_response_after_clarification = generate_response(new_prompt_for_gemini)

                        if agent_response_after_clarification.startswith("[HANDOFF]"):
                            handoff_message_from_gemini = agent_response_after_clarification.replace("[HANDOFF]", "").strip()
                            if handoff_message_from_gemini:
                                full_handoff_message = f"Agent (ARTEX): {handoff_message_from_gemini} Il semble que j'aie encore besoin d'aide pour répondre. Je vous mets en relation avec un conseiller."
                            else:
                                full_handoff_message = "Agent (ARTEX): Même avec ces précisions, il serait préférable de parler à un conseiller pour cette situation. Je vous mets en relation."
                            print(full_handoff_message)
                            speak_french(full_handoff_message)
                            print("Conversation terminée après tentative de clarification infructueuse.")
                            break # Exit the loop
                        elif agent_response_after_clarification.startswith("[CLARIFY]"):
                            # Gemini still needs clarification - treat as handoff
                            handoff_message = "Agent (ARTEX): J'ai encore besoin de précisions, et pour éviter de vous faire répéter, il serait peut-être mieux de parler directement à un conseiller. Je vous mets en relation."
                            print(handoff_message)
                            speak_french(handoff_message)
                            print("Conversation terminée après clarifications multiples.")
                            break # Exit the loop
                        else:
                            # Successful response after clarification
                            print(f"Agent (ARTEX) (texte): {agent_response_after_clarification}")
                            speak_french(agent_response_after_clarification)
                    else:
                        no_clarification_message = "Agent (ARTEX): Pas de précision fournie. Veuillez reposer votre question ou demander à parler à un conseiller si vous êtes bloqué."
                        print(no_clarification_message)
                        speak_french(no_clarification_message)
                else:
                    # Process response as usual if no clarification or handoff needed initially
                    print(f"Agent (ARTEX) (texte): {agent_response}")
                    speak_french(agent_response)

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
