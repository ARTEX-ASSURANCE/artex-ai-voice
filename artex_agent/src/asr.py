import asyncio
import speech_recognition as sr
from typing import AsyncGenerator, Optional

DEFAULT_LANGUAGE = "fr-FR"
DEFAULT_SILENCE_TIMEOUT = 4  # seconds for recognizer.listen timeout
DEFAULT_PHRASE_TIME_LIMIT = 15 # seconds for recognizer.listen phrase_time_limit
DEFAULT_ADJUST_DURATION = 0.5 # seconds for ambient noise adjustment

class ASRService:
    def __init__(self, device_index: Optional[int] = None):
        self.recognizer = sr.Recognizer()
        # Consider dynamic energy adjustment based on initial tests.
        # If background noise is relatively constant, one-time adjustment might be better.
        # If it's highly variable, dynamic might be preferred but can sometimes be too sensitive.
        self.recognizer.dynamic_energy_threshold = True # Defaulting to True
        self.recognizer.pause_threshold = 0.8 # Default is 0.8, can be tuned
        self.device_index = device_index
        # print(f"ASRService initialized. Mic index: {self.device_index if self.device_index is not None else 'Default'}. Dynamic energy: {self.recognizer.dynamic_energy_threshold}")

    async def adjust_for_ambient_noise(self, duration: float = DEFAULT_ADJUST_DURATION):
        """Adjusts for ambient noise using the configured microphone."""
        # This should be called when the microphone is known and ideally once at startup
        # if dynamic_energy_threshold is False or needs a baseline.
        # If dynamic_energy_threshold = True, this might be less critical but can still help.
        try:
            # Using a new Microphone instance for adjustment as it's a short operation
            with sr.Microphone(device_index=self.device_index) as source:
                print(f"ASR: Adjusting for ambient noise for {duration}s...")
                await asyncio.to_thread(self.recognizer.adjust_for_ambient_noise, source, duration=duration)
                print(f"ASR: Ambient noise adjustment complete. Energy threshold: {self.recognizer.energy_threshold:.2f}")
        except Exception as e:
            print(f"ASR: Could not adjust for ambient noise: {e}")


    async def listen_for_speech(
        self,
        silence_timeout: int = DEFAULT_SILENCE_TIMEOUT,
        phrase_time_limit: Optional[int] = DEFAULT_PHRASE_TIME_LIMIT
    ) -> AsyncGenerator[Optional[str], None]:

        # print(f"ASR: Listening... (silence_timeout={silence_timeout}s, phrase_limit={phrase_time_limit}s)")

        audio_data: Optional[sr.AudioData] = None
        # text_result: Optional[str] = None # Not needed here

        try:
            # It's generally better to open the microphone context just before listening
            # and close it afterwards, rather than keeping it open in self.microphone.
            with sr.Microphone(device_index=self.device_index) as source:
                loop = asyncio.get_event_loop()
                try:
                    # print("ASR: Calling recognizer.listen...")
                    audio_data = await loop.run_in_executor(
                        None, # Uses default ThreadPoolExecutor
                        lambda: self.recognizer.listen(
                            source,
                            timeout=silence_timeout,
                            phrase_time_limit=phrase_time_limit
                        )
                    )
                    # print("ASR: recognizer.listen call returned.")
                except sr.WaitTimeoutError:
                    # print(f"ASR: No speech detected within {silence_timeout}s silence timeout (WaitTimeoutError).")
                    yield "[ASR_SILENCE_TIMEOUT]" # Specific signal for silence timeout
                    return

            if audio_data:
                # print("ASR: Audio captured, attempting recognition...")
                try:
                    text_result = await loop.run_in_executor( # loop already defined
                        None,
                        lambda: self.recognizer.recognize_google(audio_data, language=DEFAULT_LANGUAGE)
                    )
                    # print(f"ASR: Recognition result: '{text_result}'")
                    yield text_result # Might be empty string if speech was unintelligible noise
                except sr.UnknownValueError:
                    # print("ASR: Google Speech Recognition could not understand audio.")
                    yield "[ASR_UNKNOWN_VALUE]" # Audio was not intelligible speech
                except sr.RequestError as e:
                    print(f"ASR: Could not request results from Google service; {e}")
                    yield f"[ASR_REQUEST_ERROR:{e}]"
                except Exception as e: # Other unexpected errors during recognition
                    print(f"ASR: Unexpected error during speech recognition: {e}")
                    yield f"[ASR_RECOGNIZE_ERROR:{e}]"
            else:
                # This case should be hit if listen() returned None without WaitTimeoutError,
                # or if WaitTimeoutError was not caught properly (it is now).
                # print("ASR: No audio data captured (audio_data is None after listen).")
                if not audio_data and silence_timeout: # If listen timed out but didn't raise WaitTimeoutError explicitly returning None
                    yield "[ASR_SILENCE_TIMEOUT]" # Should be covered by WaitTimeoutError
                else:
                    yield "[ASR_NO_AUDIO_CAPTURED]"

        except Exception as e: # Errors related to microphone access or other setup
            print(f"ASR: An error occurred in listen_for_speech (e.g., microphone issue): {e}")
            yield f"[ASR_LISTEN_SETUP_ERROR:{e}]"

        # The generator yields one result (text or signal or None) then stops.

async def main_test_asr():
    print("Starting ASR Test. Speak into the microphone. Say 'quitter' to exit.")
    mic_idx = None

    try:
        # Test if microphone is accessible at all
        with sr.Microphone(device_index=mic_idx) as m:
            print(f"ASR Test: Using microphone: {m.device_index} (Sample rate: {m.SAMPLE_RATE}, Width: {m.SAMPLE_WIDTH})")
    except Exception as e_mic_init:
        print(f"ASR Test: CRITICAL - Failed to initialize microphone (index {mic_idx if mic_idx is not None else 'Default'}). Error: {e_mic_init}")
        print("Please ensure a microphone is connected and permissions are granted.")
        print("You can list microphones using: `python -m speech_recognition`")
        return

    asr_service = ASRService(device_index=mic_idx)
    # Optional: Perform one-time ambient noise adjustment if desired.
    # await asr_service.adjust_for_ambient_noise(duration=1)

    for i in range(5): # Run a few listen attempts
        print(f"\nASR Test Attempt {i+1}/5: Speak now (or say 'quitter' to exit early)...")
        final_text = None
        async for text_chunk in asr_service.listen_for_speech(silence_timeout=5, phrase_time_limit=10):
            final_text = text_chunk
            break

        if final_text:
            if final_text.startswith("[ASR_"):
                print(f"ASR Test - Signal/Error: {final_text}")
                if final_text == "[ASR_SILENCE_TIMEOUT]":
                    print("ASR Test: Timeout - no speech detected in the allowed time.")
            else:
                print(f"ASR Test - Recognized: '{final_text}'")
                if "quitter" in final_text.lower():
                    print("ASR Test: 'quitter' detected. Exiting test loop.")
                    break
        else:
            # This case (final_text is None) means the generator yielded an explicit None
            print("ASR Test - No speech recognized or an unhandled None was yielded.")

        if i < 4 : await asyncio.sleep(0.5) # Brief pause between attempts

    print("\nASR Test finished.")

if __name__ == "__main__":
    from dotenv import load_dotenv # For GEMINI_API_KEY if any part of ASR implicitly uses it (it shouldn't)
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path)
        # print(f"ASR Test: .env file loaded from {dotenv_path}")
    else:
        # print(f"ASR Test: Warning - .env file not found at {dotenv_path}.")
        pass

    try:
        asyncio.run(main_test_asr())
    except KeyboardInterrupt:
        print("\nASR Test ended by user.")
    except Exception as e:
        print(f"ASR Test failed to run: {e}")
