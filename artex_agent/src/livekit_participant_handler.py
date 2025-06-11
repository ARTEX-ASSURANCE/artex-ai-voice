import asyncio
import grpc
from typing import Optional, AsyncGenerator, Dict, Any # Added Dict, Any
from urllib.parse import urlparse
import os
import time
from pydub import AudioSegment
from pathlib import Path

# Local imports
from artex_agent.src.tts import TTSService
from artex_agent.src.asr import ASRService

# Import placeholder stubs
try:
    from .livekit_rtc_stubs import livekit_rtc_pb2 as rtc_pb2
    from .livekit_rtc_stubs import livekit_rtc_pb2_grpc as rtc_pb2_grpc
    STUBS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import LiveKit RTC stubs: {e}. LiveKitParticipantHandler will be non-functional.")
    STUBS_AVAILABLE = False
    class rtc_pb2:
        SignalRequest = type('SignalRequest', (), {'__init__': lambda s, join=None, leave=None, add_track=None, offer=None, answer=None, trickle=None, mute=None, subscription=None, track_setting=None, update_layers=None, subscription_permission=None, sync_state=None, simulate_scenario=None, ping_req=None, update_participant_metadata=None: None, 'SerializeToString': lambda s: b''})
        SignalResponse = type('SignalResponse', (), {'FromString': lambda s: type('SignalResponse', (), {'join':None, 'participant_update':None, 'track_published':None, 'speakers_changed':None, 'leave':None, 'track_unsubscribed':None, 'token_refresh':None, 'connection_quality':None})()})
        JoinRequest = type('JoinRequest', (), {'__init__': lambda s, token=None, room_name=None, identity=None, options=None: None})
        Room = type('Room', (), {'__init__': lambda s, name="default", sid="RM_default": None})
        ParticipantInfo = type('ParticipantInfo', (), {'__init__': lambda s, sid="PA_default", identity="default_id", name="Default Name": None, 'state':0, 'is_speaking':False})
        TrackInfo = type('TrackInfo', (), {'__init__': lambda s, sid="TR_default", name="default_track", type=0, participant_sid="PA_default":None}) # type 0 for AUDIO
        LeaveRequest = type('LeaveRequest', (), {})
        AddTrackRequest = type('AddTrackRequest', (), {})
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
USER_SILENCE_HANGUP_SECONDS = 30 # seconds
SILENCE_MONITOR_INTERVAL = 5 # seconds


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

        print(f"LKPH initialized for {participant_identity} in room {room_name}. Target: {self.grpc_target}.")
        if not STUBS_AVAILABLE:
            print("LKPH: CRITICAL - gRPC stubs are not available.")

    def _derive_grpc_target(self, ws_url: str) -> str:
        parsed_url = urlparse(ws_url)
        hostname = parsed_url.hostname
        if not hostname: raise ValueError("Could not parse hostname from LiveKit WS URL.")
        default_port = 443
        port_to_use = parsed_url.port if parsed_url.port else default_port
        return f"{hostname}:{port_to_use}"

    async def _generate_signal_requests(self) -> AsyncGenerator[rtc_pb2.SignalRequest, None]:
        if not STUBS_AVAILABLE: yield rtc_pb2.SignalRequest(); return
        print(f"LKPH ({self.participant_identity}): Sending Join request...")
        join_msg = rtc_pb2.SignalRequest(
            join=rtc_pb2.JoinRequest(token=self.token)
        )
        yield join_msg
        try:
            while not self._is_disconnected_event.is_set():
                await asyncio.sleep(10)
                if self._is_disconnected_event.is_set(): break
        except asyncio.CancelledError: pass # Expected on disconnect
        finally: print(f"LKPH ({self.participant_identity}): Signal request generator finished.")

    async def _monitor_user_silence(self):
        print(f"LKPH ({self.participant_identity}): Silence monitor started.")
        try:
            while not self._is_disconnected_event.is_set():
                await asyncio.sleep(SILENCE_MONITOR_INTERVAL)
                if self._is_disconnected_event.is_set(): break

                if self.welcome_message_played and self.last_user_activity_time:
                    current_time = asyncio.get_event_loop().time()
                    if current_time - self.last_user_activity_time > USER_SILENCE_HANGUP_SECONDS:
                        print(f"LKPH ({self.participant_identity}): User silence timeout of {USER_SILENCE_HANGUP_SECONDS}s reached. Disconnecting.")
                        await self.publish_tts_audio_to_room("Déconnexion en raison d'une période d'inactivité. Au revoir.")
                        await asyncio.sleep(2) # Allow TTS to play
                        await self.disconnect() # This will set _is_disconnected_event and stop this loop
                        break
        except asyncio.CancelledError:
            print(f"LKPH ({self.participant_identity}): Silence monitor task cancelled.")
        finally:
            print(f"LKPH ({self.participant_identity}): Silence monitor task finished.")


    async def _event_loop(self):
        if not self.rtc_stub or not self.rtc_stub.Signal or not STUBS_AVAILABLE:
            print("LKPH: RTC stub/Signal not available."); self._is_disconnected_event.set(); return

        print(f"LKPH ({self.participant_identity}): Event loop starting...")
        try:
            self._is_disconnected_event.clear()
            response_stream = self.rtc_stub.Signal(self._generate_signal_requests())
            async for response in response_stream:
                if self._is_disconnected_event.is_set(): break

                if response.join: # Actual JoinResponse from server
                    jr = response.join; room_info = jr.room; pi = jr.participant
                    print(f"LK Evt ({self.participant_identity}): Successfully joined room: {room_info.name} (SID: {room_info.sid})")
                    print(f"LK Evt ({self.participant_identity}): My Participant Info: SID={pi.sid}, Identity={pi.identity}, Name={pi.name}")
                    if not self.welcome_message_played:
                        await self.publish_tts_audio_to_room(WELCOME_MESSAGE_TEXT)
                        self.welcome_message_played = True
                        self.last_user_activity_time = asyncio.get_event_loop().time()

                elif response.track_published and response.track_published.track:
                    tp_info = response.track_published; track_info = tp_info.track
                    print(f"LK Evt ({self.participant_identity}): Track Published: SID={track_info.sid}, Name={track_info.name}, Type={track_info.type}, ParticipantSID={tp_info.participant_sid}")

                    is_remote_audio = (track_info.type == 0 and tp_info.participant_sid != self.participant_identity) # Assuming type 0 is AUDIO
                    if is_remote_audio:
                        print(f"LK Evt: Remote audio track {track_info.sid} from {tp_info.participant_sid}. Simulating ASR.")
                        self.subscribed_audio_tracks[track_info.sid] = track_info

                        # Simulate audio frame reception and ASR
                        dummy_audio_bytes = b'\x00\x01' * (48000 * 2 * 1 * 2) # 2s of 48kHz, 16bit, mono
                        if self.asr_service:
                            transcribed_text = await self.asr_service.transcribe_audio_frames(dummy_audio_bytes, 48000, 2)
                            if transcribed_text and not transcribed_text.startswith("[ASR_"):
                                print(f"LK Evt (Simulated ASR from {tp_info.participant_sid}): '{transcribed_text}'")
                                self.last_user_activity_time = asyncio.get_event_loop().time()
                                # TODO: Queue this text for agent.py's main loop
                            else:
                                print(f"LK Evt (Simulated ASR from {tp_info.participant_sid}): No transcription or ASR signal: {transcribed_text}")
                elif response.leave:
                    print(f"LK Evt ({self.participant_identity}): Leave acknowledged by server."); self._is_disconnected_event.set(); break
                # Add other event handlers (participant_update, speakers_changed, etc.) as needed

        except grpc.aio.AioRpcError as e: print(f"LKPH ({self.participant_identity}): gRPC error in event loop: {e.code()} - {e.details()}")
        except asyncio.CancelledError: print(f"LKPH ({self.participant_identity}): Event loop cancelled.")
        except Exception as e: print(f"LKPH ({self.participant_identity}): Unexpected error in event loop: {e}")
        finally: self._is_disconnected_event.set(); print(f"LKPH ({self.participant_identity}): Event loop terminated.")

    async def connect(self) -> bool:
        if not STUBS_AVAILABLE: return False
        if not self.livekit_ws_url or not self.token:
            print("LKPH: URL or Token not provided."); return False

        self.last_user_activity_time = None # Reset on new connection
        self.welcome_message_played = False # Reset on new connection

        print(f"LKPH ({self.participant_identity}): Connecting to {self.grpc_target}")
        try:
            self.channel = grpc.aio.secure_channel(self.grpc_target, grpc.ssl_channel_credentials())
            self.rtc_stub = rtc_pb2_grpc.RTCServiceStub(self.channel)
            print("LKPH: gRPC Channel and Stub created.")

            self.event_loop_task = asyncio.create_task(self._event_loop())
            self.silence_monitor_task = asyncio.create_task(self._monitor_user_silence()) # Start silence monitor

            print(f"LKPH ({self.participant_identity}): Connection initiated. Event & silence monitor loops started.")
            return True
        except Exception as e:
            print(f"LKPH ({self.participant_identity}): Connect failed: {e}")
            if self.channel: await self.channel.close()
            return False

    async def publish_tts_audio_to_room(self, text_to_speak: str):
        # ... (implementation from previous step) ...
        if not self.tts_service: print("LKPH: TTSService not available."); return
        if not self.channel or not self.rtc_stub or self._is_disconnected_event.is_set():
            print("LKPH: Not connected. Cannot publish TTS."); return
        mp3_filepath_str = await self.tts_service.get_speech_audio_filepath(text_to_speak)
        if not mp3_filepath_str: print(f"LKPH ({self.participant_identity}): TTS failed."); return
        mp3_filepath = Path(mp3_filepath_str)
        if not mp3_filepath.exists(): print(f"LKPH ({self.participant_identity}): TTS MP3 not at {mp3_filepath}."); return
        # print(f"LKPH ({self.participant_identity}): TTS MP3 at {mp3_filepath}. Converting...")
        try:
            audio_segment = AudioSegment.from_mp3(mp3_filepath)
            audio_segment = audio_segment.set_channels(TARGET_CHANNELS).set_frame_rate(TARGET_SAMPLE_RATE).set_sample_width(TARGET_SAMPLE_WIDTH)
            pcm_data = audio_segment.raw_data
            # print(f"LKPH ({self.participant_identity}): Converted to PCM: {len(pcm_data)} bytes")
            if not self.active_audio_track_cid:
                self.active_audio_track_cid = f"track_tts_{os.urandom(4).hex()}"
                print(f"LKPH ({self.participant_identity}): Would send AddTrackRequest for CID {self.active_audio_track_cid} (simulated).")
            print(f"LKPH ({self.participant_identity}): Would stream PCM for TTS '{text_to_speak[:30]}...' (simulated).")
        except FileNotFoundError: print(f"LKPH ({self.participant_identity}): ERROR - FFmpeg not found for pydub MP3 support.")
        except Exception as e: print(f"LKPH ({self.participant_identity}): Error publishing audio: {e}")

    async def handle_incoming_audio_stream(self, track_sid: str, audio_stream_iterator: AsyncGenerator[bytes, None]):
        print(f"LKPH ({self.participant_identity}): handle_incoming_audio_stream for {track_sid} (Placeholder)")
        await asyncio.sleep(0.1)

    async def disconnect(self):
        print(f"LKPH ({self.participant_identity}): Disconnecting...")
        self._is_disconnected_event.set()

        tasks_to_cancel = []
        if self.event_loop_task and not self.event_loop_task.done():
            tasks_to_cancel.append(self.event_loop_task)
        if self.silence_monitor_task and not self.silence_monitor_task.done():
            tasks_to_cancel.append(self.silence_monitor_task)

        for task in tasks_to_cancel:
            task.cancel()
            try: await task
            except asyncio.CancelledError: print(f"LKPH ({self.participant_identity}): Task {task.get_name()} successfully cancelled.")
            except Exception as e: print(f"LKPH ({self.participant_identity}): Exception awaiting cancelled task {task.get_name()}: {e}")

        self.event_loop_task = None
        self.silence_monitor_task = None

        if self.channel:
            await self.channel.close()
            print(f"LKPH ({self.participant_identity}): gRPC Channel closed.")

        self.channel = None; self.rtc_stub = None
        print(f"LKPH ({self.participant_identity}): Disconnected and resources released.")

async def main_test_participant_handler():
    # ... (main_test_participant_handler from previous step, ensuring it passes ASRService)
    from dotenv import load_dotenv
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    if not os.path.exists(dotenv_path): dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path): load_dotenv(dotenv_path=dotenv_path); print(f"Test: Loaded .env from {dotenv_path}")
    else: print(f"Test: .env file not found.")

    lk_url = os.getenv("LIVEKIT_URL")
    lk_api_key = os.getenv("LIVEKIT_API_KEY")
    lk_api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not all([lk_url, lk_api_key, lk_api_secret]):
        print("LiveKit credentials not set. Skipping test."); return

    test_room = "arthextest_ph_full"
    test_identity = f"agent_full_ph_tester_{os.urandom(3).hex()}"

    from livekit import AccessToken, VideoGrant
    grant = VideoGrant(room_join=True, room=test_room, can_publish=True, can_subscribe=True)
    token_obj = AccessToken(lk_api_key, lk_api_secret, identity=test_identity, ttl=300, name="TestFullHandler")
    token_obj.grants = grant
    test_token = token_obj.to_jwt()
    print(f"Test: Generated token for '{test_identity}' in room '{test_room}'.")

    try:
        tts_service_instance = TTSService()
        asr_service_instance = ASRService()
    except Exception as e:
        print(f"Test: Failed to initialize TTS/ASR Service: {e}"); return

    handler = LiveKitParticipantHandler(
        livekit_ws_url=lk_url, token=test_token, room_name=test_room,
        participant_identity=test_identity, tts_service=tts_service_instance,
        asr_service=asr_service_instance
    )

    if await handler.connect():
        print("Test: Participant handler connect reported success. Event loop and silence monitor running (simulated).")
        # Simulate initial delay for welcome message to be "played" and activity timer started
        await asyncio.sleep(3)

        # Simulate no activity to test silence hangup
        # The USER_SILENCE_HANGUP_SECONDS is 30, monitor checks every 5.
        # So, wait for a bit longer than that.
        print(f"Test: Simulating user silence for {USER_SILENCE_HANGUP_SECONDS + SILENCE_MONITOR_INTERVAL + 2} seconds to test hangup...")
        await asyncio.sleep(USER_SILENCE_HANGUP_SECONDS + SILENCE_MONITOR_INTERVAL + 2)

        # If disconnect was called by silence monitor, event_loop_task should be done or cancelled
        if handler.event_loop_task and not handler.event_loop_task.done():
             print("Test: Silence hangup might not have triggered as expected, manually disconnecting.")
             await handler.disconnect() # Ensure disconnect is called if silence monitor didn't
        else:
             print("Test: Silence hangup likely triggered or connection ended by other means.")
    else:
        print("Test: Participant handler connect failed.")

if __name__ == "__main__":
    asyncio.run(main_test_participant_handler())
