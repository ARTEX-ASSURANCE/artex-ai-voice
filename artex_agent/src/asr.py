import asyncio
import speech_recognition as sr
from typing import AsyncGenerator, Optional
import os # For dotenv in main_test_asr

# Import logging configuration
from .logging_config import get_logger # Assuming it's in the same directory (src)
log = get_logger(__name__)

DEFAULT_LANGUAGE = "fr-FR"
DEFAULT_SILENCE_TIMEOUT = 4
DEFAULT_PHRASE_TIME_LIMIT = 15
DEFAULT_ADJUST_DURATION = 0.5

class ASRService:
    def __init__(self, device_index: Optional[int] = None):
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        self.device_index = device_index
        log.info("ASRService initialized.", mic_index=(self.device_index if self.device_index is not None else 'Default'),
                 dynamic_energy=self.recognizer.dynamic_energy_threshold,
                 pause_threshold=self.recognizer.pause_threshold)

    async def adjust_for_ambient_noise(self, duration: float = DEFAULT_ADJUST_DURATION):
        try:
            with sr.Microphone(device_index=self.device_index) as source:
                log.info(f"Adjusting for ambient noise.", duration=duration, mic_index=source.device_index)
                await asyncio.to_thread(self.recognizer.adjust_for_ambient_noise, source, duration=duration)
                log.info(f"Ambient noise adjustment complete.", energy_threshold=f"{self.recognizer.energy_threshold:.2f}")
        except Exception as e:
            log.error("Could not adjust for ambient noise.", error=str(e), exc_info=True)

    async def _recognize_audio_async(self, audio_data: sr.AudioData) -> Optional[str]:
        loop = asyncio.get_event_loop()
        try:
            text = await loop.run_in_executor(
                None,
                lambda: self.recognizer.recognize_google(audio_data, language=DEFAULT_LANGUAGE)
            )
            return text
        except sr.UnknownValueError:
            log.info("ASR: Google Speech Recognition could not understand audio.")
            return None
        except sr.RequestError as e:
            log.error(f"ASR: Could not request results from Google service.", error=str(e))
            return f"[ASR_REQUEST_ERROR:{e}]"
        except Exception as e:
            log.error(f"ASR: Unexpected error during speech recognition.", error=str(e), exc_info=True)
            return f"[ASR_RECOGNIZE_ERROR:{e}]"

    async def listen_for_speech(
        self,
        silence_timeout: int = DEFAULT_SILENCE_TIMEOUT,
        phrase_time_limit: Optional[int] = DEFAULT_PHRASE_TIME_LIMIT
    ) -> AsyncGenerator[Optional[str], None]:
        audio_data: Optional[sr.AudioData] = None
        try:
            with sr.Microphone(device_index=self.device_index) as source:
                # log.debug(f"ASR: Listening on mic {source.device_index} (timeout={silence_timeout}s, phrase_limit={phrase_time_limit}s)...")
                loop = asyncio.get_event_loop()
                try:
                    audio_data = await loop.run_in_executor(
                        None,
                        lambda: self.recognizer.listen(
                            source,
                            timeout=silence_timeout,
                            phrase_time_limit=phrase_time_limit
                        )
                    )
                except sr.WaitTimeoutError:
                    log.info("ASR: Silence timeout during listen.")
                    yield "[ASR_SILENCE_TIMEOUT]"
                    return

            if audio_data:
                # log.debug("ASR: Audio captured, attempting recognition.")
                recognized_text = await self._recognize_audio_async(audio_data)
                if recognized_text is None:
                    yield "[ASR_UNKNOWN_VALUE]"
                else:
                    yield recognized_text
            else: # Should ideally be caught by WaitTimeoutError
                log.warn("ASR: No audio data captured, though WaitTimeoutError was not raised.")
                if silence_timeout:
                    yield "[ASR_SILENCE_TIMEOUT]"
                else:
                    yield "[ASR_NO_AUDIO_CAPTURED]"
        except Exception as e:
            log.error(f"ASR: Error in listen_for_speech (e.g., microphone access).", error=str(e), exc_info=True)
            yield f"[ASR_LISTEN_SETUP_ERROR:{e}]"

    async def transcribe_audio_frames(
        self,
        audio_frames_bytes: bytes,
        sample_rate: int,
        sample_width: int
    ) -> Optional[str]:
        if not audio_frames_bytes:
            log.warn("ASR: No audio frames provided for transcription.")
            return "[ASR_NO_FRAMES_PROVIDED]"

        # log.debug(f"ASR: Transcribing frames.", num_bytes=len(audio_frames_bytes), sr=sample_rate, sw=sample_width)
        try:
            if not self.recognizer:
                 log.error("ASR: Recognizer not initialized for transcribe_audio_frames.")
                 raise ValueError("Recognizer not available in ASRService")

            audio_data = sr.AudioData(audio_frames_bytes, sample_rate, sample_width)
            recognized_text = await self._recognize_audio_async(audio_data)

            if recognized_text is None:
                return "[ASR_UNKNOWN_VALUE]"
            return recognized_text

        except ValueError as ve:
            log.error("ASR: Error creating AudioData from frames.", error=str(ve), exc_info=True)
            return "[ASR_AUDIODATA_ERROR]"
        except Exception as e:
            log.error("ASR: Error transcribing frames.", error=str(e), exc_info=True)
            return f"[ASR_TRANSCRIBE_ERROR:{e}]"

async def main_test_asr():
    from dotenv import load_dotenv

    # Ensure logging is set up for the test if run standalone
    # This is a bit circular if logging_config itself is being tested,
    # but for module tests, it's good to have consistent logging.
    # If this script is run directly, logging_config.py might not have been imported by an entry point.
    # However, get_logger() at module level in this file will use a basic config if none is set.
    # For robust testing of this file standalone, explicitly set up:
    # current_dir = Path(__file__).parent.resolve()
    # project_root = current_dir.parent
    # sys.path.insert(0, str(project_root))
    # from src.logging_config import setup_logging as test_setup_logging
    # test_setup_logging() # Use default console for test output clarity

    log.info("Starting ASR Test. Speak into the microphone. Say 'quitter' to exit.")
    mic_idx = None

    try:
        with sr.Microphone(device_index=mic_idx) as m:
            log.info(f"ASR Test: Using microphone.", mic_index=m.device_index, sample_rate=m.SAMPLE_RATE, sample_width=m.SAMPLE_WIDTH)
    except Exception as e_mic_init:
        log.critical(f"ASR Test: Failed to initialize microphone.", mic_index=(mic_idx if mic_idx is not None else 'Default'), error=str(e_mic_init), exc_info=True)
        print("CRITICAL: Mic init failed. Ensure mic connected & permissions granted. List mics via `python -m speech_recognition`", file=sys.stderr)
        return

    asr_service = ASRService(device_index=mic_idx)
    # await asr_service.adjust_for_ambient_noise(duration=1) # Optional

    for i in range(3):
        log.info(f"ASR Test Attempt {i+1}/3 (Listen from Mic): Speak now...")
        print(f"\nASR Test Attempt {i+1}/3: Speak now...") # User-facing prompt
        final_text_mic = None
        async for text_chunk in asr_service.listen_for_speech(silence_timeout=3, phrase_time_limit=5):
            final_text_mic = text_chunk
            break

        if final_text_mic:
            if final_text_mic.startswith("[ASR_"):
                log.warn("ASR Test (Mic) - Signal/Error.", signal=final_text_mic)
                print(f"ASR Test (Mic) - Signal/Error: {final_text_mic}") # User-facing
            else:
                log.info("ASR Test (Mic) - Recognized.", text=final_text_mic)
                print(f"ASR Test (Mic) - Recognized: '{final_text_mic}'") # User-facing
                if "quitter" in final_text_mic.lower():
                    log.info("ASR Test: 'quitter' detected. Exiting test loop.")
                    break
        else:
            log.warn("ASR Test (Mic) - No text or signal returned.")
            print("ASR Test (Mic) - No text or signal returned.") # User-facing

        if i < 2 : await asyncio.sleep(0.5)

    log.info("ASR Test: Testing transcribe_audio_frames with dummy (silent) audio data.")
    print("\nASR Test: Testing transcribe_audio_frames with dummy (silent) audio data.") # User-facing
    sr_test, sw_test, duration_test, num_channels_test = 16000, 2, 2, 1
    silent_frames = b'\x00' * (sr_test * sw_test * num_channels_test * duration_test)

    transcribed_from_frames = await asr_service.transcribe_audio_frames(silent_frames, sr_test, sw_test)
    if transcribed_from_frames:
        if transcribed_from_frames.startswith("[ASR_"):
            log.info("ASR Test (from_frames) - Signal/Error for silent frames (expected).", signal=transcribed_from_frames)
            print(f"ASR Test (from_frames) - Signal/Error for silent frames: '{transcribed_from_frames}' (This is expected)") # User-facing
        else:
            log.warn("ASR Test (from_frames) - Unexpectedly Recognized from silent frames.", text=transcribed_from_frames)
            print(f"ASR Test (from_frames) - Unexpectedly Recognized: '{transcribed_from_frames}' from silent frames.") # User-facing
    else:
        log.error("ASR Test (from_frames) - Got None, expected specific ASR signal.")
        print("ASR Test (from_frames) - Got None, expected signal like [ASR_UNKNOWN_VALUE].") # User-facing

    log.info("ASR Test finished.")
    print("\nASR Test finished.", file=sys.stderr)


if __name__ == "__main__":
    # Ensure .env is loaded for standalone test if any config is needed indirectly
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path): load_dotenv(dotenv_path=dotenv_path)

    # Setup basic logging for standalone test if logging_config.py is not run by main app
    # This helps see logs from get_logger(__name__) at the top of this file.
    # If this file is run directly, `setup_logging()` from `logging_config` won't be called by an entry point.
    # So, we do a minimal local setup for the test.
    if not logging.getLogger().handlers: # Check if root logger has handlers
        structlog.configure(
            processors=[structlog.dev.ConsoleRenderer()],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), stream=sys.stdout)
        log.info("Minimal logging configured for asr.py standalone test.")


    try:
        asyncio.run(main_test_asr())
    except KeyboardInterrupt:
        log.info("ASR Test ended by user.")
        print("\nASR Test ended by user.", file=sys.stderr)
    except Exception as e:
        log.critical("ASR Test failed to run.", error=str(e), exc_info=True)
        print(f"ASR Test failed to run: {e}", file=sys.stderr)
