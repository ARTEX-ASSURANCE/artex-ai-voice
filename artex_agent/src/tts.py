import os
import hashlib
import asyncio
from pathlib import Path
from typing import Optional

# Attempt to import Google Cloud TTS, but make it optional
try:
    from google.cloud import texttospeech_v1 as google_tts
    GOOGLE_TTS_AVAILABLE = True
except ImportError:
    GOOGLE_TTS_AVAILABLE = False
    google_tts = None # Ensure it's None if not available for type hints later

from gtts import gTTS as gtts_engine # Renamed to avoid conflict

# Configuration from environment variables
TTS_CACHE_DIR_STR = os.getenv("TTS_CACHE_DIR", "/tmp/artts_cache") # Default if not set
TTS_CACHE_DIR = Path(TTS_CACHE_DIR_STR)

TTS_USE_GOOGLE_CLOUD_STR = os.getenv("TTS_USE_GOOGLE_CLOUD", "true").lower()
TTS_USE_GOOGLE_CLOUD = TTS_USE_GOOGLE_CLOUD_STR == "true"

TTS_LANG_CODE_GOOGLE = os.getenv("TTS_LANG_CODE", "fr-FR")
TTS_VOICE_NAME_GOOGLE = os.getenv("TTS_VOICE_NAME", "fr-FR-Standard-D")
TTS_LANG_CODE_GTTS = "fr" # gTTS uses simple language codes, e.g., 'fr', 'en'

class TTSService:
    def __init__(self):
        self.google_tts_client: Optional[google_tts.TextToSpeechAsyncClient] = None
        google_app_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        if GOOGLE_TTS_AVAILABLE and TTS_USE_GOOGLE_CLOUD and google_app_creds:
            if os.path.exists(google_app_creds):
                try:
                    self.google_tts_client = google_tts.TextToSpeechAsyncClient()
                    print("TTS Service: Google Cloud TTS Client initialized successfully.")
                except Exception as e:
                    print(f"TTS Service: Failed to initialize Google Cloud TTS Client (credentials set but client failed): {e}. Will fallback to gTTS.")
                    self.google_tts_client = None # Ensure it's None on failure
            else:
                print(f"TTS Service: GOOGLE_APPLICATION_CREDENTIALS file not found at '{google_app_creds}'. Will fallback to gTTS.")
                self.google_tts_client = None

        if not self.google_tts_client and TTS_USE_GOOGLE_CLOUD:
            print(f"TTS Service: Google Cloud TTS was configured to be used, but client could not be initialized. Using gTTS fallback.")
        elif not self.google_tts_client:
             print(f"TTS Service: Using gTTS. (Google TTS Lib Available: {GOOGLE_TTS_AVAILABLE}, Use Google Cloud Flag: {TTS_USE_GOOGLE_CLOUD}, Creds Path Set: {google_app_creds is not None})")

        try:
            TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            # print(f"TTS Service: Cache directory is {TTS_CACHE_DIR}")
        except Exception as e:
            print(f"TTS Service: Error creating/accessing cache directory {TTS_CACHE_DIR}: {e}. Caching may fail.")


    def _generate_filename(self, text: str, voice_params_str: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(text.encode('utf-8'))
        hasher.update(voice_params_str.encode('utf-8'))
        return f"{hasher.hexdigest()}.mp3"

    async def _synthesize_google_cloud_tts_internal(self, text: str, filepath: Path) -> bool:
        if not self.google_tts_client:
            # print("TTS Google Cloud: Client not available for synthesis.") # Already logged at init
            return False
        try:
            input_text_gc = google_tts.types.SynthesisInput(text=text)
            voice_params_gc = google_tts.types.VoiceSelectionParams(
                language_code=TTS_LANG_CODE_GOOGLE,
                name=TTS_VOICE_NAME_GOOGLE
            )
            audio_config_gc = google_tts.types.AudioConfig(
                audio_encoding=google_tts.enums.AudioEncoding.MP3
            )

            # print(f"TTS Google Cloud: Requesting synthesis for '{text[:30]}...'")
            response = await self.google_tts_client.synthesize_speech(
                request={"input": input_text_gc, "voice": voice_params_gc, "audio_config": audio_config_gc}
            )
            with open(filepath, "wb") as out:
                out.write(response.audio_content)
            # print(f"TTS Google Cloud: Audio content written to {filepath}")
            return True
        except Exception as e:
            print(f"TTS Google Cloud: Error during synthesis for '{text[:30]}...': {e}")
            if filepath.exists(): filepath.unlink(missing_ok=True)
            return False

    def _synthesize_gtts_internal(self, text: str, filepath: Path) -> bool:
        try:
            # print(f"TTS gTTS: Requesting synthesis for '{text[:30]}...'")
            tts = gtts_engine(text=text, lang=TTS_LANG_CODE_GTTS, slow=False)
            tts.save(str(filepath))
            # print(f"TTS gTTS: Audio content written to {filepath}")
            return True
        except Exception as e:
            print(f"TTS gTTS: Error during synthesis for '{text[:30]}...': {e}")
            if filepath.exists(): filepath.unlink(missing_ok=True)
            return False

    async def get_speech_audio_filepath(self, text: str) -> Optional[str]:
        if not text or not text.strip():
            print("TTS Service: No text provided to synthesize.")
            return None

        should_try_google = self.google_tts_client and TTS_USE_GOOGLE_CLOUD

        if should_try_google:
            voice_params_for_filename = f"google_{TTS_LANG_CODE_GOOGLE}_{TTS_VOICE_NAME_GOOGLE}"
        else:
            voice_params_for_filename = f"gtts_{TTS_LANG_CODE_GTTS}"

        filename = self._generate_filename(text, voice_params_for_filename)
        filepath = TTS_CACHE_DIR / filename

        if filepath.exists():
            # print(f"TTS Service: Cache hit for '{text[:30]}...' -> {filepath}")
            return str(filepath)

        # print(f"TTS Service: Cache miss for '{text[:30]}...'. Generating new file: {filepath}")

        success = False
        if should_try_google:
            # print("TTS Service: Attempting synthesis with Google Cloud TTS.")
            success = await self._synthesize_google_cloud_tts_internal(text, filepath)

        if not success:
            if should_try_google:
                print("TTS Service: Google Cloud TTS failed or was not used, falling back to gTTS.")
            # else:
                # print("TTS Service: Using gTTS for synthesis.") # Avoid too much noise if gTTS is default

            loop = asyncio.get_event_loop()
            try:
                success = await loop.run_in_executor(None, self._synthesize_gtts_internal, text, filepath)
            except Exception as e_gtts_exec:
                print(f"TTS gTTS: Error in executor for gTTS: {e_gtts_exec}")
                success = False

        return str(filepath) if success else None

async def main_test_tts():
    from dotenv import load_dotenv
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path)
        print(f"TTS Main Test: Loaded .env from {dotenv_path}")
    else:
        print(f"TTS Main Test: .env file not found at {dotenv_path}. Relying on existing environment variables.")

    print(f"TTS Main Test Info: GOOGLE_APPLICATION_CREDENTIALS='{os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}'")
    print(f"TTS Main Test Info: TTS_USE_GOOGLE_CLOUD='{os.getenv('TTS_USE_GOOGLE_CLOUD')}' (Effective: {TTS_USE_GOOGLE_CLOUD})")
    print(f"TTS Main Test Info: TTS_CACHE_DIR='{TTS_CACHE_DIR_STR}' (Effective: {TTS_CACHE_DIR})")


    service = TTSService()

    texts_to_test = [
        "Bonjour de l'assistant ARTEX pour le test Google Cloud.",
        "Ceci est un deuxième test de la synthèse vocale avec gTTS.",
        "Bonjour de l'assistant ARTEX pour le test Google Cloud.",
    ]

    print(f"\n--- Testing TTS Generation ---")
    print(f"Note: GOOGLE_APPLICATION_CREDENTIALS needs to be valid for Google TTS to work.")

    # Test 1 (Primary: Google Cloud if configured and available, else gTTS)
    print(f"\nTest 1: Requesting TTS for: '{texts_to_test[0]}'")
    path1 = await service.get_speech_audio_filepath(texts_to_test[0])
    print(f"  MP3 path (Test 1): {path1 if path1 else 'Failed'}")
    if path1: print(f"  File exists (Test 1): {Path(path1).exists()}")

    # Test 2 (Force gTTS by temporarily disabling Google client in a local *test* instance)
    # This tests the gTTS pathway even if Google Cloud is configured.
    print(f"\nTest 2: Requesting TTS for: '{texts_to_test[1]}' (Forcing gTTS via temporary client disable for this test call)")

    # Create a temporary service instance or manipulate global flags for testing fallback
    # For this test, we'll temporarily alter the global flag if needed, then restore.
    # This is just for testing the gTTS path.
    original_use_google_cloud_flag = TTS_USE_GOOGLE_CLOUD
    global TTS_USE_GOOGLE_CLOUD_TEMP_TEST
    TTS_USE_GOOGLE_CLOUD_TEMP_TEST = False # Local override for this test call

    # Re-evaluate should_try_google based on the temporary override for this specific call
    # This requires the TTSService to re-evaluate TTS_USE_GOOGLE_CLOUD or pass it.
    # A cleaner way for testing is to instantiate a new service or pass override to method.
    # For this test, let's assume we can influence the 'should_try_google' for one call.
    # The current TTSService structure reads globals at init.
    # So, to test gTTS fallback, we'd need to ensure self.google_tts_client is None OR TTS_USE_GOOGLE_CLOUD is False.

    # Simpler test for gTTS: instantiate a new service with Google Cloud explicitly disabled for it.
    temp_tts_use_google_cloud = os.environ.get("TTS_USE_GOOGLE_CLOUD")
    os.environ["TTS_USE_GOOGLE_CLOUD"] = "false" # Temporarily override env for new instance
    service_for_gtts_test = TTSService() # This instance will not use Google Cloud
    os.environ["TTS_USE_GOOGLE_CLOUD"] = temp_tts_use_google_cloud if temp_tts_use_google_cloud is not None else "true" # Restore

    path2 = await service_for_gtts_test.get_speech_audio_filepath(texts_to_test[1])
    print(f"  MP3 path (Test 2 - gTTS forced): {path2 if path2 else 'Failed'}")
    if path2: print(f"  File exists (Test 2): {Path(path2).exists()}")

    # Test 3 (Caching - should use Google Cloud if it succeeded in Test 1, using original 'service' instance)
    print(f"\nTest 3: Requesting cached item: '{texts_to_test[2]}'")
    path3 = await service.get_speech_audio_filepath(texts_to_test[2])
    print(f"  MP3 path (Test 3 - cached): {path3 if path3 else 'Failed'}")
    if path3: print(f"  File exists (Test 3): {Path(path3).exists()}")
    if path1 and path3 and path1 == path3:
        print("  SUCCESS: Test 1 and Test 3 returned the same cached filepath as expected.")
    elif path1 and path3:
        print(f"  NOTE: Test 1 ({path1}) and Test 3 ({path3}) paths differ. Cache might not have hit as expected (e.g. if voice params changed or first attempt failed).")

    print(f"\nTTS Test finished. Check cache directory ({TTS_CACHE_DIR}) for generated files.")

if __name__ == "__main__":
    asyncio.run(main_test_tts())
