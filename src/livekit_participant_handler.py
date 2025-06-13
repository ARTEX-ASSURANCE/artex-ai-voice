import asyncio
import grpc
from typing import Optional, AsyncGenerator, Dict, Any
from urllib.parse import urlparse
import os
import time
from pydub import AudioSegment
from pathlib import Path

# Local imports
from artex_agent.src.tts import TTSService
from artex_agent.src.asr import ASRService
from .logging_config import get_logger # Assuming logging_config is in src/

log = get_logger(__name__)

# Import placeholder stubs
try:
    from .livekit_rtc_stubs import livekit_rtc_pb2 as rtc_pb2
    from .livekit_rtc_stubs import livekit_rtc_pb2_grpc as rtc_pb2_grpc
    STUBS_AVAILABLE = True
    log.debug("LiveKit RTC stubs imported successfully.")
except ImportError as e:
    log.warn("Could not import LiveKit RTC stubs. LiveKitParticipantHandler will be non-functional.", error=str(e))
    STUBS_AVAILABLE = False
    class rtc_pb2:
        SignalRequest = type('SignalRequest', (), {'__init__': lambda s, join=None, leave=None, add_track=None, offer=None, answer=None, trickle=None, mute=None, subscription=None, track_setting=None, update_layers=None, subscription_permission=None, sync_state=None, simulate_scenario=None, ping_req=None, update_participant_metadata=None: None, 'SerializeToString': lambda s: b''})
        SignalResponse = type('SignalResponse', (), {'FromString': lambda s: type('SignalResponse', (), {'join':None, 'participant_update':None, 'track_published':None, 'speakers_changed':None, 'leave':None, 'track_unsubscribed':None, 'token_refresh':None, 'connection_quality':None})()})
        JoinRequest = type('JoinRequest', (), {'__init__': lambda s, token=None, room_name=None, identity=None, options=None: None}) # Added room_name, identity
        Room = type('Room', (), {'__init__': lambda s, name="default", sid="RM_default": None})
        ParticipantInfo = type('ParticipantInfo', (), {'__init__': lambda s, sid="PA_default", identity="default_id", name="Default Name": None, 'state':0, 'is_speaking':False})
        TrackInfo = type('TrackInfo', (), {'__init__': lambda s, sid="TR_default", name="default_track", type=0, participant_sid="PA_default":None})
        LeaveRequest = type('LeaveRequest', (), {})
        AddTrackRequest = type('AddTrackRequest', (), {'__init__':lambda s, cid=None, name=None, type=None, source=None: None})
        AudioFrame = type('AudioFrame', (), {})
        TrackPublishedResponse = type('TrackPublishedResponse', (), {'__init__': lambda s, participant_sid=None, track=None: None})
        ParticipantUpdate = type('ParticipantUpdate', (), {'__init__': lambda s, participants=None: None})
        SpeakersChanged = type('SpeakersChanged', (), {'__init__': lambda s, speakers=None: None})
        LeaveResponse = type('LeaveResponse', (), {})
    class rtc_pb2_grpc: RTCServiceStub = type('RTCServiceStub', (), {'__init__': lambda s, c: None, 'Signal': None})

TARGET_SAMPLE_RATE = 48000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2
FRAME_DURATION_MS = 20
SAMPLES_PER_FRAME = int(TARGET_SAMPLE_RATE * FRAME_DURATION_MS / 1000)
BYTES_PER_FRAME = SAMPLES_PER_FRAME * TARGET_CHANNELS * TARGET_SAMPLE_WIDTH

WELCOME_MESSAGE_TEXT = "Bonjour, vous êtes connecté à l'assistant ARTEX. Comment puis-je vous aider?"
USER_SILENCE_HANGUP_SECONDS = 30
SILENCE_MONITOR_INTERVAL = 5


class LiveKitParticipantHandler:
    def __init__(self, livekit_ws_url: str, token: str, room_name: str,
                 participant_identity: str, tts_service: TTSService, asr_service: ASRService):
        self.livekit_ws_url = livekit_ws_url
        self.token = token
        self.room_name = room_name
        self.participant_identity = participant_identity
        self.tts_service = tts_service
        self.asr_service = asr_service

        self.grpc_target = self._derive_grpc_target(livekit_ws_url)

        self.channel: Optional[grpc.aio.Channel] = None
        self.rtc_stub: Optional[rtc_pb2_grpc.RTCServiceStub] = None
        self.event_loop_task: Optional[asyncio.Task] = None
        self.silence_monitor_task: Optional[asyncio.Task] = None
        self._is_disconnected_event = asyncio.Event()
        self.active_audio_track_cid: Optional[str] = None
        self.subscribed_audio_tracks: Dict[str, Any] = {}

        self.welcome_message_played = False
        self.last_user_activity_time: Optional[float] = None

        log.info("LiveKitParticipantHandler initialized.", identity=participant_identity, room=room_name, grpc_target=self.grpc_target)
        if not STUBS_AVAILABLE:
            log.critical("LiveKitParticipantHandler: gRPC stubs are not available. Functionality will be impaired.")

    def _derive_grpc_target(self, ws_url: str) -> str:
        parsed_url = urlparse(ws_url)
        hostname = parsed_url.hostname
        if not hostname:
            log.error("Could not parse hostname from LiveKit WS URL.", url=ws_url)
            raise ValueError("Could not parse hostname from LiveKit WS URL.")
        default_port = 443
        port_to_use = parsed_url.port if parsed_url.port else default_port
        return f"{hostname}:{port_to_use}"

    async def _generate_signal_requests(self) -> AsyncGenerator[rtc_pb2.SignalRequest, None]:
        if not STUBS_AVAILABLE:
            log.error("Cannot generate signal requests: gRPC stubs missing.")
            yield rtc_pb2.SignalRequest(); return

        log.info("Sending Join request.", participant_identity=self.participant_identity)
        join_msg = rtc_pb2.SignalRequest(
            join=rtc_pb2.JoinRequest(token=self.token)
        )
        yield join_msg
        try:
            while not self._is_disconnected_event.is_set():
                await asyncio.sleep(10)
                if self._is_disconnected_event.is_set(): break
        except asyncio.CancelledError:
            log.info("Signal request generator cancelled.", participant_identity=self.participant_identity)
        finally:
            log.info("Signal request generator finished.", participant_identity=self.participant_identity)

    async def _monitor_user_silence(self):
        log.info("Silence monitor started.", participant_identity=self.participant_identity)
        try:
            while not self._is_disconnected_event.is_set():
                await asyncio.sleep(SILENCE_MONITOR_INTERVAL)
                if self._is_disconnected_event.is_set(): break

                if self.welcome_message_played and self.last_user_activity_time:
                    current_time = asyncio.get_event_loop().time()
                    if current_time - self.last_user_activity_time > USER_SILENCE_HANGUP_SECONDS:
                        log.warn("User silence timeout reached. Disconnecting.", participant_identity=self.participant_identity, timeout_seconds=USER_SILENCE_HANGUP_SECONDS)
                        await self.publish_tts_audio_to_room("Déconnexion en raison d'une période d'inactivité. Au revoir.")
                        await asyncio.sleep(2)
                        await self.disconnect()
                        break
        except asyncio.CancelledError:
            log.info("Silence monitor task cancelled.", participant_identity=self.participant_identity)
        finally:
            log.info("Silence monitor task finished.", participant_identity=self.participant_identity)

    async def _event_loop(self):
        if not self.rtc_stub or not self.rtc_stub.Signal or not STUBS_AVAILABLE:
            log.error("RTC stub or Signal method not available. Cannot start event loop.", participant_identity=self.participant_identity)
            self._is_disconnected_event.set(); return

        log.info("Event loop starting...", participant_identity=self.participant_identity)
        try:
            self._is_disconnected_event.clear()
            response_stream = self.rtc_stub.Signal(self._generate_signal_requests())
            async for response in response_stream:
                if self._is_disconnected_event.is_set(): break

                if response.join:
                    jr = response.join; room_info = jr.room; pi = jr.participant
                    log.info("Joined LiveKit room.", room_name=room_info.name, room_sid=room_info.sid,
                             participant_sid=pi.sid, participant_identity=pi.identity, participant_name=pi.name)
                    if not self.welcome_message_played:
                        await self.publish_tts_audio_to_room(WELCOME_MESSAGE_TEXT)
                        self.welcome_message_played = True
                        self.last_user_activity_time = asyncio.get_event_loop().time()
                elif response.track_published and response.track_published.track:
                    tp_info = response.track_published; track_info = tp_info.track
                    log.info("Track published.", track_sid=track_info.sid, track_name=track_info.name,
                             track_type=track_info.type, participant_sid=tp_info.participant_sid,
                             participant_identity=self.participant_identity) # Assuming track_info has participant_identity

                    is_remote_audio = (track_info.type == 0 and hasattr(tp_info, 'participant_sid') and tp_info.participant_sid != self.participant_identity) # Check against self.participant_identity if tp_info.participant_identity not available
                    if is_remote_audio:
                        log.info("Remote audio track published. Simulating ASR.", track_sid=track_info.sid, remote_participant_sid=tp_info.participant_sid)
                        self.subscribed_audio_tracks[track_info.sid] = track_info
                        dummy_audio_bytes = b'\x00\x01' * (48000 * 2 * 1 * 1) # 1s dummy audio
                        if self.asr_service:
                            transcribed_text = await self.asr_service.transcribe_audio_frames(dummy_audio_bytes, 48000, 2)
                            if transcribed_text and not transcribed_text.startswith("[ASR_"):
                                log.info("Simulated ASR from remote track.", track_sid=track_info.sid, text=transcribed_text)
                                self.last_user_activity_time = asyncio.get_event_loop().time()
                                # TODO: Queue this text for agent.py's main loop
                            else:
                                log.warn("No transcription or ASR signal from simulated remote track.", track_sid=track_info.sid, asr_result=transcribed_text)
                elif response.leave:
                    log.info("Leave acknowledged by server.", participant_identity=self.participant_identity)
                    self._is_disconnected_event.set(); break
                # Add other event type logging (participant_update, speakers_changed, etc.)

        except grpc.aio.AioRpcError as e:
            log.error("gRPC error in event loop.", code=e.code(), details=e.details(), participant_identity=self.participant_identity, exc_info=True)
        except asyncio.CancelledError:
            log.info("Event loop cancelled.", participant_identity=self.participant_identity)
        except Exception as e:
            log.error("Unexpected error in event loop.", error=str(e), participant_identity=self.participant_identity, exc_info=True)
        finally:
            self._is_disconnected_event.set()
            log.info("Event loop terminated.", participant_identity=self.participant_identity)

    async def connect(self) -> bool:
        if not STUBS_AVAILABLE: log.error("Cannot connect: gRPC stubs missing."); return False
        if not self.livekit_ws_url or not self.token:
            log.error("Cannot connect: LiveKit URL or Token not provided."); return False

        self.last_user_activity_time = None
        self.welcome_message_played = False

        log.info("Connecting to gRPC target.", grpc_target=self.grpc_target, participant_identity=self.participant_identity)
        try:
            self.channel = grpc.aio.secure_channel(self.grpc_target, grpc.ssl_channel_credentials())
            self.rtc_stub = rtc_pb2_grpc.RTCServiceStub(self.channel)
            log.info("gRPC Channel and Stub created.", participant_identity=self.participant_identity)

            self.event_loop_task = asyncio.create_task(self._event_loop())
            self.silence_monitor_task = asyncio.create_task(self._monitor_user_silence())

            log.info("Connection process initiated. Event & silence monitor loops started.", participant_identity=self.participant_identity)
            return True
        except Exception as e:
            log.error("Failed to connect or create stub.", error=str(e), participant_identity=self.participant_identity, exc_info=True)
            if self.channel: await self.channel.close()
            return False

    async def publish_tts_audio_to_room(self, text_to_speak: str):
        if not self.tts_service: log.warn("TTSService not available in handler."); return
        if not self.channel or not self.rtc_stub or self._is_disconnected_event.is_set():
            log.warn("Cannot publish TTS: Not connected or gRPC issue.", participant_identity=self.participant_identity); return

        log.info("Preparing TTS for LiveKit.", text_snippet=text_to_speak[:30], participant_identity=self.participant_identity)
        mp3_filepath_str = await self.tts_service.get_speech_audio_filepath(text_to_speak)

        if not mp3_filepath_str: log.error("TTS failed to generate audio file.", text_snippet=text_to_speak[:30]); return
        mp3_filepath = Path(mp3_filepath_str)
        if not mp3_filepath.exists(): log.error("TTS MP3 file does not exist.", path=str(mp3_filepath)); return

        log.debug(f"TTS MP3 generated, converting to PCM.", path=str(mp3_filepath))
        try:
            audio_segment = AudioSegment.from_mp3(mp3_filepath)
            audio_segment = audio_segment.set_channels(TARGET_CHANNELS).set_frame_rate(TARGET_SAMPLE_RATE).set_sample_width(TARGET_SAMPLE_WIDTH)
            pcm_data = audio_segment.raw_data
            log.debug(f"Converted to PCM.", pcm_data_length=len(pcm_data), participant_identity=self.participant_identity)

            if not self.active_audio_track_cid: # Conceptual track publishing
                self.active_audio_track_cid = f"track_tts_{os.urandom(4).hex()}"
                log.info(f"Would send AddTrackRequest for TTS audio track.", cid=self.active_audio_track_cid, participant_identity=self.participant_identity)
            log.info(f"Would stream PCM data for TTS (simulated).", cid=self.active_audio_track_cid, data_length=len(pcm_data), participant_identity=self.participant_identity)
        except FileNotFoundError:
            log.error("FFmpeg not found for pydub MP3 support. Cannot publish TTS audio.", exc_info=True)
        except Exception as e:
            log.error("Error processing or simulating audio publishing for TTS.", error=str(e), exc_info=True)

    async def handle_incoming_audio_stream(self, track_sid: str, audio_stream_iterator: AsyncGenerator[bytes, None]):
        log.info("handle_incoming_audio_stream called (Placeholder).", track_sid=track_sid, participant_identity=self.participant_identity)
        await asyncio.sleep(0.1)

    async def disconnect(self):
        log.info("Disconnecting participant handler.", participant_identity=self.participant_identity)
        self._is_disconnected_event.set()

        tasks_to_cancel = []
        if self.event_loop_task and not self.event_loop_task.done(): tasks_to_cancel.append(self.event_loop_task)
        if self.silence_monitor_task and not self.silence_monitor_task.done(): tasks_to_cancel.append(self.silence_monitor_task)

        for task in tasks_to_cancel:
            task.cancel()
            try: await task
            except asyncio.CancelledError: log.info(f"Task cancelled successfully.", task_name=task.get_name(), participant_identity=self.participant_identity)
            except Exception as e: log.error(f"Exception awaiting cancelled task.", task_name=task.get_name(), error=str(e), participant_identity=self.participant_identity, exc_info=True)

        self.event_loop_task = None; self.silence_monitor_task = None
        if self.channel:
            await self.channel.close()
            log.info("gRPC Channel closed.", participant_identity=self.participant_identity)
        self.channel = None; self.rtc_stub = None
        log.info("Disconnected and resources released.", participant_identity=self.participant_identity)

async def main_test_participant_handler():
    from dotenv import load_dotenv
    # Ensure logging is set up for the test
    if not logging.getLogger().handlers or not structlog.is_configured():
        import logging; import structlog; import sys
        structlog.configure(processors=[structlog.dev.ConsoleRenderer()])
        logging.basicConfig(level="DEBUG", stream=sys.stdout) # Use DEBUG for more test verbosity
        log.info("Minimal logging re-configured for livekit_participant_handler.py standalone test.")

    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    if not os.path.exists(dotenv_path): dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path): load_dotenv(dotenv_path=dotenv_path); log.info(f"Test: Loaded .env from {dotenv_path}")
    else: log.warn("Test: .env file not found. Relying on env vars.")

    lk_url = os.getenv("LIVEKIT_URL")
    lk_api_key = os.getenv("LIVEKIT_API_KEY")
    lk_api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not all([lk_url, lk_api_key, lk_api_secret]):
        log.critical("LiveKit credentials not set. Skipping participant handler test."); return

    test_room = "arthextest_ph_full_v2"
    test_identity = f"agent_ph_logger_tester_{os.urandom(3).hex()}"

    try:
        from livekit import AccessToken, VideoGrant
        grant = VideoGrant(room_join=True, room=test_room, can_publish=True, can_subscribe=True)
        token_obj = AccessToken(lk_api_key, lk_api_secret, identity=test_identity, ttl=300, name="TestFullHandlerWithLogging")
        token_obj.grants = grant
        test_token = token_obj.to_jwt()
        log.info(f"Test: Generated token.", identity=test_identity, room=test_room)
    except Exception as e:
        log.critical("Test: Failed to generate test token.", error=str(e), exc_info=True); return

    try:
        tts_service_instance = TTSService()
        asr_service_instance = ASRService()
    except Exception as e:
        log.critical(f"Test: Failed to initialize TTS/ASR Service.", error=str(e), exc_info=True); return

    handler = LiveKitParticipantHandler(
        livekit_ws_url=lk_url, token=test_token, room_name=test_room,
        participant_identity=test_identity, tts_service=tts_service_instance,
        asr_service=asr_service_instance
    )

    if await handler.connect():
        log.info("Test: Participant handler connect reported success.")
        await asyncio.sleep(3)
        await handler.publish_tts_audio_to_room("Bonjour, ceci est un test audio de l'agent Arthex via LiveKit et gRPC, maintenant avec structlog.")
        log.info(f"Test: Simulating user silence for {USER_SILENCE_HANGUP_SECONDS + SILENCE_MONITOR_INTERVAL + 2} seconds to test hangup...")
        await asyncio.sleep(USER_SILENCE_HANGUP_SECONDS + SILENCE_MONITOR_INTERVAL + 2)

        if handler.event_loop_task and not handler.event_loop_task.done():
             log.warn("Test: Silence hangup might not have triggered as expected, manually disconnecting.")
             await handler.disconnect()
        else:
             log.info("Test: Silence hangup likely triggered or connection ended by other means.")
    else:
        log.error("Test: Participant handler connect failed.")

if __name__ == "__main__":
    import logging # For standalone test logging setup
    import structlog # For standalone test logging setup
    asyncio.run(main_test_participant_handler())
