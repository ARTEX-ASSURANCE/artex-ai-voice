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
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        self.device_index = device_index
        # print(f"ASRService initialized. Mic index: {self.device_index if self.device_index is not None else 'Default'}. Dynamic energy: {self.recognizer.dynamic_energy_threshold}")

    async def adjust_for_ambient_noise(self, duration: float = DEFAULT_ADJUST_DURATION):
        try:
            with sr.Microphone(device_index=self.device_index) as source:
                print(f"ASR: Adjusting for ambient noise for {duration}s...")
                await asyncio.to_thread(self.recognizer.adjust_for_ambient_noise, source, duration=duration)
                print(f"ASR: Ambient noise adjustment complete. Energy threshold: {self.recognizer.energy_threshold:.2f}")
        except Exception as e:
            print(f"ASR: Could not adjust for ambient noise: {e}")

    async def _recognize_audio_async(self, audio_data: sr.AudioData) -> Optional[str]:
        loop = asyncio.get_event_loop()
        try:
            text = await loop.run_in_executor(
                None,
                lambda: self.recognizer.recognize_google(audio_data, language=DEFAULT_LANGUAGE)
            )
            return text
        except sr.UnknownValueError:
            # print("ASR: Google Speech Recognition could not understand audio.") # Handled by caller with signal
            return None # Will be converted to [ASR_UNKNOWN_VALUE] by caller
        except sr.RequestError as e:
            print(f"ASR: Could not request results from Google service; {e}")
            return f"[ASR_REQUEST_ERROR:{e}]" # Return specific error signal
        except Exception as e:
            print(f"ASR: Unexpected error during speech recognition: {e}")
            return f"[ASR_RECOGNIZE_ERROR:{e}]" # Return specific error signal


    async def listen_for_speech(
        self,
        silence_timeout: int = DEFAULT_SILENCE_TIMEOUT,
        phrase_time_limit: Optional[int] = DEFAULT_PHRASE_TIME_LIMIT
    ) -> AsyncGenerator[Optional[str], None]:
        audio_data: Optional[sr.AudioData] = None
        try:
            with sr.Microphone(device_index=self.device_index) as source:
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
                    yield "[ASR_SILENCE_TIMEOUT]"
                    return

            if audio_data:
                recognized_text = await self._recognize_audio_async(audio_data)
                if recognized_text is None: # Specifically from UnknownValueError in _recognize_audio_async
                    yield "[ASR_UNKNOWN_VALUE]"
                else: # This includes actual text or error signals from _recognize_audio_async
                    yield recognized_text
            else:
                if not audio_data and silence_timeout:
                    yield "[ASR_SILENCE_TIMEOUT]"
                else:
                    yield "[ASR_NO_AUDIO_CAPTURED]"
        except Exception as e:
            print(f"ASR: An error occurred in listen_for_speech (e.g., microphone issue): {e}")
            yield f"[ASR_LISTEN_SETUP_ERROR:{e}]"

    async def transcribe_audio_frames(
        self,
        audio_frames_bytes: bytes,
        sample_rate: int,
        sample_width: int
    ) -> Optional[str]:
        if not audio_frames_bytes:
            print("ASR Service: No audio frames provided for transcription.")
            return "[ASR_NO_FRAMES_PROVIDED]"

        # print(f"ASR Service: Transcribing {len(audio_frames_bytes)} bytes of audio data (SR={sample_rate}, SW={sample_width}).")
        try:
            if not self.recognizer:
                 raise ValueError("Recognizer not available in ASRService")

            audio_data = sr.AudioData(audio_frames_bytes, sample_rate, sample_width)
            recognized_text = await self._recognize_audio_async(audio_data)

            if recognized_text is None: # From UnknownValueError
                return "[ASR_UNKNOWN_VALUE]"
            # _recognize_audio_async already returns error signals like [ASR_REQUEST_ERROR:...]
            return recognized_text

        except ValueError as ve:
            print(f"ASR Service: Error creating AudioData (likely parameter issue): {ve}")
            return "[ASR_AUDIODATA_ERROR]"
        except Exception as e:
            print(f"ASR Service: Error transcribing frames: {e}")
            return f"[ASR_TRANSCRIBE_ERROR:{e}]"

async def main_test_asr():
    import os # Required for dotenv path
    from dotenv import load_dotenv # For GEMINI_API_KEY if any part of ASR implicitly uses it (it shouldn't)

    print("Starting ASR Test. Speak into the microphone. Say 'quitter' to exit.")
    mic_idx = None

    try:
        with sr.Microphone(device_index=mic_idx) as m:
            print(f"ASR Test: Using microphone: {m.device_index} (Sample rate: {m.SAMPLE_RATE}, Width: {m.SAMPLE_WIDTH})")
    except Exception as e_mic_init:
        print(f"ASR Test: CRITICAL - Failed to initialize microphone. Error: {e_mic_init}")
        return

    asr_service = ASRService(device_index=mic_idx)
    # await asr_service.adjust_for_ambient_noise(duration=1) # Optional adjustment

    for i in range(3): # Reduced attempts for brevity
        print(f"\nASR Test Attempt {i+1}/3 (Listen from Mic): Speak now...")
        final_text_mic = None
        async for text_chunk in asr_service.listen_for_speech(silence_timeout=3, phrase_time_limit=5):
            final_text_mic = text_chunk
            break

        if final_text_mic:
            if final_text_mic.startswith("[ASR_"):
                print(f"ASR Test (Mic) - Signal/Error: {final_text_mic}")
            else:
                print(f"ASR Test (Mic) - Recognized: '{final_text_mic}'")
                if "quitter" in final_text_mic.lower():
                    print("ASR Test: 'quitter' detected. Exiting test loop.")
                    break
        else:
            print("ASR Test (Mic) - No text or signal returned (should yield signal for errors).")

        if i < 2 : await asyncio.sleep(0.5)

    print("\nASR Test: Testing transcribe_audio_frames with dummy (silent) audio data.")
    sr_test = 16000
    sw_test = 2
    duration_test = 2
    num_channels_test = 1
    silent_frames = b'\x00' * (sr_test * sw_test * num_channels_test * duration_test)

    transcribed_from_frames = await asr_service.transcribe_audio_frames(silent_frames, sr_test, sw_test)
    if transcribed_from_frames:
        if transcribed_from_frames.startswith("[ASR_"):
            print(f"ASR Test (from_frames) - Signal/Error for silent frames: '{transcribed_from_frames}' (This is expected, e.g., UNKNOWN_VALUE)")
        else: # Should ideally not happen for pure silence with Google Speech API
            print(f"ASR Test (from_frames) - Unexpectedly Recognized: '{transcribed_from_frames}' from silent frames.")
    else:
        # This means _recognize_audio_async itself returned None, which transcribe_audio_frames should convert to [ASR_UNKNOWN_VALUE]
        print("ASR Test (from_frames) - Got None, expected specific ASR signal like [ASR_UNKNOWN_VALUE] for silent frames.")


    # Test with some actual (though still dummy) data that isn't pure silence
    # This would require a .wav file or generating more meaningful PCM data.
    # For now, the silence test primarily checks the pathway.
    # To make it more realistic, one might load a short WAV file's bytes.
    # Example:
    # try:
    #     with sr.AudioFile("path_to_sample.wav") as source_file:
    #         audio_content = source_file.record(source_file)
    #     print("\nASR Test: Testing transcribe_audio_frames with WAV file data.")
    #     transcribed_from_file_frames = await asr_service.transcribe_audio_frames(
    #         audio_content.frame_data,
    #         audio_content.sample_rate,
    #         audio_content.sample_width
    #     )
    #     print(f"ASR Test (from_file_frames) - Recognized: '{transcribed_from_file_frames}'")
    # except Exception as e_wav:
    #     print(f"ASR Test: Could not test with WAV file: {e_wav}")


    print("\nASR Test finished.")

if __name__ == "__main__":
    # Ensure .env is loaded if any underlying libraries implicitly need env vars, though ASRService itself doesn't directly.
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path): load_dotenv(dotenv_path=dotenv_path)

    try:
        asyncio.run(main_test_asr())
    except KeyboardInterrupt:
        print("\nASR Test ended by user.")
    except Exception as e:
        print(f"ASR Test failed to run: {e}")
