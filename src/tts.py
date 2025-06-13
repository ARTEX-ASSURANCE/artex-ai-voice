import os
import hashlib
import asyncio
from pathlib import Path
from typing import Optional
import sys # For standalone test logging

# Import logging configuration
from .logging_config import get_logger # Assuming it's in the same directory (src)
log = get_logger(__name__)

# Attempt to import Google Cloud TTS, but make it optional
try:
    from google.cloud import texttospeech_v1 as google_tts
    GOOGLE_TTS_AVAILABLE = True
except ImportError:
    GOOGLE_TTS_AVAILABLE = False
    google_tts = None

from gtts import gTTS as gtts_engine

# Configuration from environment variables
TTS_CACHE_DIR_STR = os.getenv("TTS_CACHE_DIR", "/tmp/artts_cache")
TTS_CACHE_DIR = Path(TTS_CACHE_DIR_STR)

TTS_USE_GOOGLE_CLOUD_STR = os.getenv("TTS_USE_GOOGLE_CLOUD", "true").lower()
TTS_USE_GOOGLE_CLOUD = TTS_USE_GOOGLE_CLOUD_STR == "true"

TTS_LANG_CODE_GOOGLE = os.getenv("TTS_LANG_CODE", "fr-FR")
TTS_VOICE_NAME_GOOGLE = os.getenv("TTS_VOICE_NAME", "fr-FR-Standard-D")
TTS_LANG_CODE_GTTS = "fr"

class TTSService:
    def __init__(self):
        self.google_tts_client: Optional[google_tts.TextToSpeechAsyncClient] = None
        google_app_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        if GOOGLE_TTS_AVAILABLE and TTS_USE_GOOGLE_CLOUD and google_app_creds:
            if os.path.exists(google_app_creds):
                try:
                    self.google_tts_client = google_tts.TextToSpeechAsyncClient()
                    log.info("Google Cloud TTS Client initialized successfully.")
                except Exception as e:
                    log.error("Failed to initialize Google Cloud TTS Client (creds set but client failed). Will fallback to gTTS.", error=str(e), exc_info=True)
                    self.google_tts_client = None
            else:
                log.warn(f"GOOGLE_APPLICATION_CREDENTIALS file not found.", path=google_app_creds, fallback_to_gtts=True)
                self.google_tts_client = None

        if not self.google_tts_client and TTS_USE_GOOGLE_CLOUD:
            log.warn("Google Cloud TTS was configured to be used, but client could not be initialized. Using gTTS fallback.")
        elif not self.google_tts_client:
             log.info("Using gTTS for Text-to-Speech.", google_tts_available=GOOGLE_TTS_AVAILABLE, use_google_cloud_flag=TTS_USE_GOOGLE_CLOUD, creds_path_set=(google_app_creds is not None))

        try:
            TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            log.info(f"TTS cache directory is {TTS_CACHE_DIR}")
        except Exception as e:
            log.error(f"Error creating/accessing cache directory.", cache_dir=str(TTS_CACHE_DIR), error=str(e), exc_info=True)


    def _generate_filename(self, text: str, voice_params_str: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(text.encode('utf-8'))
        hasher.update(voice_params_str.encode('utf-8'))
        return f"{hasher.hexdigest()}.mp3"

    async def _synthesize_google_cloud_tts_internal(self, text: str, filepath: Path) -> bool:
        if not self.google_tts_client:
            log.warn("Google Cloud TTS client not available for synthesis.")
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

            log.debug(f"Requesting Google Cloud TTS synthesis.", text_snippet=text[:30])
            response = await self.google_tts_client.synthesize_speech(
                request={"input": input_text_gc, "voice": voice_params_gc, "audio_config": audio_config_gc}
            )
            with open(filepath, "wb") as out:
                out.write(response.audio_content)
            log.debug(f"Google Cloud TTS audio content written.", path=str(filepath))
            return True
        except Exception as e:
            log.error(f"Google Cloud TTS synthesis error.", text_snippet=text[:30], error=str(e), exc_info=True)
            if filepath.exists(): filepath.unlink(missing_ok=True)
            return False

    def _synthesize_gtts_internal(self, text: str, filepath: Path) -> bool:
        try:
            log.debug(f"Requesting gTTS synthesis.", text_snippet=text[:30])
            tts = gtts_engine(text=text, lang=TTS_LANG_CODE_GTTS, slow=False)
            tts.save(str(filepath))
            log.debug(f"gTTS audio content written.", path=str(filepath))
            return True
        except Exception as e:
            log.error(f"gTTS synthesis error.", text_snippet=text[:30], error=str(e), exc_info=True)
            if filepath.exists(): filepath.unlink(missing_ok=True)
            return False

    async def get_speech_audio_filepath(self, text: str) -> Optional[str]:
        if not text or not text.strip():
            log.warn("No text provided to synthesize.")
            return None

        should_try_google = self.google_tts_client and TTS_USE_GOOGLE_CLOUD

        if should_try_google:
            voice_params_for_filename = f"google_{TTS_LANG_CODE_GOOGLE}_{TTS_VOICE_NAME_GOOGLE}"
        else:
            voice_params_for_filename = f"gtts_{TTS_LANG_CODE_GTTS}"

        filename = self._generate_filename(text, voice_params_for_filename)
        filepath = TTS_CACHE_DIR / filename

        if filepath.exists():
            log.info(f"TTS cache hit.", text_snippet=text[:30], path=str(filepath))
            return str(filepath)

        log.info(f"TTS cache miss. Generating new file.", text_snippet=text[:30], path=str(filepath))

        success = False
        if should_try_google:
            log.debug("Attempting synthesis with Google Cloud TTS.")
            success = await self._synthesize_google_cloud_tts_internal(text, filepath)

        if not success:
            if should_try_google:
                log.warn("Google Cloud TTS failed or was not used, falling back to gTTS.")
            else:
                log.info("Using gTTS for synthesis.")

            loop = asyncio.get_event_loop()
            try:
                success = await loop.run_in_executor(None, self._synthesize_gtts_internal, text, filepath)
            except Exception as e_gtts_exec:
                log.error("Error in executor for gTTS.", error=str(e_gtts_exec), exc_info=True)
                success = False

        return str(filepath) if success else None

async def main_test_tts():
    from dotenv import load_dotenv

    # For standalone testing of tts.py, ensure logging is minimally configured if not already by an entry point
    if not logging.getLogger().handlers:
        structlog.configure(processors=[structlog.dev.ConsoleRenderer()])
        logging.basicConfig(level="DEBUG", stream=sys.stdout) # Use stdout for test, stderr for app setup msg
        log.info("Minimal logging configured for tts.py standalone test.")

    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path)
        log.info(f"TTS Main Test: Loaded .env from {dotenv_path}")
    else:
        log.warn(f"TTS Main Test: .env file not found at {dotenv_path}. Relying on existing environment variables.")

    log.info(f"TTS Main Test Info: GOOGLE_APPLICATION_CREDENTIALS='{os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}'")
    log.info(f"TTS Main Test Info: TTS_USE_GOOGLE_CLOUD='{os.getenv('TTS_USE_GOOGLE_CLOUD')}' (Effective: {TTS_USE_GOOGLE_CLOUD})")
    log.info(f"TTS Main Test Info: TTS_CACHE_DIR='{TTS_CACHE_DIR_STR}' (Effective: {TTS_CACHE_DIR})")

    service = TTSService()

    texts_to_test = [
        "Bonjour de l'assistant ARTEX pour le test Google Cloud.",
        "Ceci est un deuxième test de la synthèse vocale avec gTTS.",
        "Bonjour de l'assistant ARTEX pour le test Google Cloud.",
    ]

    log.info(f"--- Testing TTS Generation ---")
    log.info(f"Note: GOOGLE_APPLICATION_CREDENTIALS needs to be valid for Google TTS to work.")

    log.info(f"Test 1: Requesting TTS for: '{texts_to_test[0]}'")
    path1 = await service.get_speech_audio_filepath(texts_to_test[0])
    log.info(f"MP3 path (Test 1): {path1 if path1 else 'Failed'}", file_exists=(Path(path1).exists() if path1 else False))

    log.info(f"Test 2: Requesting TTS for: '{texts_to_test[1]}' (Forcing gTTS via temporary client disable for this test call)")
    temp_tts_use_google_cloud_env = os.environ.get("TTS_USE_GOOGLE_CLOUD")
    os.environ["TTS_USE_GOOGLE_CLOUD"] = "false"
    service_for_gtts_test = TTSService()
    if temp_tts_use_google_cloud_env is None: del os.environ["TTS_USE_GOOGLE_CLOUD"] # Clean up if it wasn't there
    else: os.environ["TTS_USE_GOOGLE_CLOUD"] = temp_tts_use_google_cloud_env # Restore

    path2 = await service_for_gtts_test.get_speech_audio_filepath(texts_to_test[1])
    log.info(f"MP3 path (Test 2 - gTTS forced): {path2 if path2 else 'Failed'}", file_exists=(Path(path2).exists() if path2 else False))

    log.info(f"Test 3: Requesting cached item: '{texts_to_test[2]}'")
    path3 = await service.get_speech_audio_filepath(texts_to_test[2])
    log.info(f"MP3 path (Test 3 - cached): {path3 if path3 else 'Failed'}", file_exists=(Path(path3).exists() if path3 else False))
    if path1 and path3 and path1 == path3:
        log.info("SUCCESS: Test 1 and Test 3 returned the same cached filepath as expected.")
    elif path1 and path3:
        log.warn("NOTE: Test 1 and Test 3 paths differ. Cache might not have hit as expected.", path1=path1, path3=path3)

    log.info(f"TTS Test finished. Check cache directory ({TTS_CACHE_DIR}) for generated files.")

if __name__ == "__main__":
    import structlog # Needed for standalone test logging setup
    asyncio.run(main_test_tts())
