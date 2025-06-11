import asyncio
import grpc
from typing import Optional, AsyncGenerator
from urllib.parse import urlparse
import os
import time
from pydub import AudioSegment # For MP3 decoding
from pathlib import Path # For filepath manipulation

# Local imports
from artex_agent.src.tts import TTSService # Assuming tts.py is in src/

# Import placeholder stubs
try:
    from .livekit_rtc_stubs import livekit_rtc_pb2 as rtc_pb2
    from .livekit_rtc_stubs import livekit_rtc_pb2_grpc as rtc_pb2_grpc
    STUBS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import LiveKit RTC stubs: {e}. LiveKitParticipantHandler will be non-functional.")
    STUBS_AVAILABLE = False
    class rtc_pb2:
        SignalRequest = type('SignalRequest', (), {'__init__': lambda s, join=None, leave=None, add_track=None: None, 'SerializeToString': lambda s: b''})
        SignalResponse = type('SignalResponse', (), {'FromString': lambda s: type('SignalResponse', (), {'join':None, 'participant_update':None, 'track_published':None, 'speakers_changed':None, 'leave':None})()})
        JoinRequest = type('JoinRequest', (), {})
        Room = type('Room', (), {})
        ParticipantInfo = type('ParticipantInfo', (), {})
        TrackInfo = type('TrackInfo', (), {})
        LeaveRequest = type('LeaveRequest', (), {})
        AddTrackRequest = type('AddTrackRequest', (), {})
        AudioFrame = type('AudioFrame', (), {})
    class rtc_pb2_grpc: RTCServiceStub = type('RTCServiceStub', (), {'__init__': lambda s, c: None, 'Signal': None})

# Placeholder audio parameters (should match LiveKit's expectations for PCM frames)
TARGET_SAMPLE_RATE = 48000  # Common for WebRTC
TARGET_CHANNELS = 1       # Mono
TARGET_SAMPLE_WIDTH = 2   # 2 bytes = 16-bit PCM
FRAME_DURATION_MS = 20    # 20ms frames, common for WebRTC
SAMPLES_PER_FRAME = int(TARGET_SAMPLE_RATE * FRAME_DURATION_MS / 1000)
BYTES_PER_FRAME = SAMPLES_PER_FRAME * TARGET_CHANNELS * TARGET_SAMPLE_WIDTH


class LiveKitParticipantHandler:
    def __init__(self, livekit_ws_url: str, token: str, room_name: str, participant_identity: str, tts_service: TTSService):
        self.livekit_ws_url = livekit_ws_url
        self.token = token
        self.room_name = room_name
        self.participant_identity = participant_identity
        self.tts_service = tts_service # Store TTSService instance

        self.grpc_target = self._derive_grpc_target(livekit_ws_url)

        self.channel: Optional[grpc.aio.Channel] = None
        self.rtc_stub: Optional[rtc_pb2_grpc.RTCServiceStub] = None
        self.event_loop_task: Optional[asyncio.Task] = None
        self._is_disconnected_event = asyncio.Event()
        self.active_audio_track_cid: Optional[str] = None # Client-generated ID for the audio track

        print(f"LiveKitParticipantHandler initialized for {participant_identity} in room {room_name}. Target: {self.grpc_target}.")
        if not STUBS_AVAILABLE:
            print("LiveKitParticipantHandler: CRITICAL - gRPC stubs are not available.")

    def _derive_grpc_target(self, ws_url: str) -> str:
        parsed_url = urlparse(ws_url)
        hostname = parsed_url.hostname
        if not hostname:
            raise ValueError("Could not parse hostname from LiveKit WS URL.")
        default_port = 443
        port_to_use = parsed_url.port if parsed_url.port else default_port
        return f"{hostname}:{port_to_use}"

    async def _generate_signal_requests(self) -> AsyncGenerator[rtc_pb2.SignalRequest, None]:
        if not STUBS_AVAILABLE: yield rtc_pb2.SignalRequest(); return # Should not happen if connect guard works

        print(f"LKPH ({self.participant_identity}): Sending Join request...")
        join_msg = rtc_pb2.SignalRequest(
            join=rtc_pb2.JoinRequest(token=self.token) # Token should contain room, identity, permissions
        )
        yield join_msg

        try:
            while not self._is_disconnected_event.is_set():
                await asyncio.sleep(10)
                if self._is_disconnected_event.is_set(): break
        except asyncio.CancelledError:
            print(f"LKPH ({self.participant_identity}): Signal request generator cancelled.")
        finally:
            print(f"LKPH ({self.participant_identity}): Signal request generator finished.")

    async def _event_loop(self):
        if not self.rtc_stub or not self.rtc_stub.Signal or not STUBS_AVAILABLE:
            print("LKPH: RTC stub/Signal not available. Cannot start event loop."); self._is_disconnected_event.set(); return

        print(f"LKPH ({self.participant_identity}): Event loop starting...")
        try:
            self._is_disconnected_event.clear()
            response_stream = self.rtc_stub.Signal(self._generate_signal_requests())
            async for response in response_stream:
                if self._is_disconnected_event.is_set(): break
                if response.join:
                    jr = response.join; room_info = jr.room; pi = jr.participant
                    print(f"LK Evt ({self.participant_identity}): Joined room: {room_info.name}, My SID: {pi.sid}")
                # ... other event handling from previous step ...
                else: pass # print(f"LK Evt ({self.participant_identity}): Unhandled signal: {response}")
        except grpc.aio.AioRpcError as e: print(f"LKPH ({self.participant_identity}): gRPC error in event loop: {e.code()} - {e.details()}")
        except asyncio.CancelledError: print(f"LKPH ({self.participant_identity}): Event loop cancelled.")
        except Exception as e: print(f"LKPH ({self.participant_identity}): Unexpected error in event loop: {e}")
        finally: self._is_disconnected_event.set(); print(f"LKPH ({self.participant_identity}): Event loop terminated.")

    async def connect(self) -> bool:
        # ... (connect logic from previous step, ensuring it uses self.grpc_target) ...
        if not STUBS_AVAILABLE: return False
        if not self.livekit_ws_url or not self.token:
            print("LKPH: URL or Token not provided."); return False
        print(f"LKPH ({self.participant_identity}): Connecting to {self.grpc_target}")
        try:
            self.channel = grpc.aio.secure_channel(self.grpc_target, grpc.ssl_channel_credentials())
            self.rtc_stub = rtc_pb2_grpc.RTCServiceStub(self.channel)
            print("LKPH: gRPC Channel and Stub created.")
            self.event_loop_task = asyncio.create_task(self._event_loop())
            print(f"LKPH ({self.participant_identity}): Connection initiated. Event loop started.")
            return True
        except Exception as e:
            print(f"LKPH ({self.participant_identity}): Connect failed: {e}")
            if self.channel: await self.channel.close()
            return False


    async def publish_tts_audio_to_room(self, text_to_speak: str):
        if not self.tts_service:
            print("LKPH: TTSService not available."); return
        if not self.channel or not self.rtc_stub or self._is_disconnected_event.is_set():
            print("LKPH: Not connected or gRPC channel/stub issue. Cannot publish TTS."); return

        print(f"LKPH ({self.participant_identity}): Preparing TTS for: '{text_to_speak[:30]}...'")
        mp3_filepath_str = await self.tts_service.get_speech_audio_filepath(text_to_speak)

        if not mp3_filepath_str:
            print(f"LKPH ({self.participant_identity}): TTS failed to generate audio file."); return

        mp3_filepath = Path(mp3_filepath_str)
        if not mp3_filepath.exists():
            print(f"LKPH ({self.participant_identity}): TTS MP3 file does not exist at {mp3_filepath}."); return

        print(f"LKPH ({self.participant_identity}): TTS MP3 generated at {mp3_filepath}. Converting to PCM...")
        try:
            audio_segment = AudioSegment.from_mp3(mp3_filepath)
            audio_segment = audio_segment.set_channels(TARGET_CHANNELS)
            audio_segment = audio_segment.set_frame_rate(TARGET_SAMPLE_RATE)
            audio_segment = audio_segment.set_sample_width(TARGET_SAMPLE_WIDTH)
            pcm_data = audio_segment.raw_data
            print(f"LKPH ({self.participant_identity}): Converted to PCM: {len(pcm_data)} bytes, SR={TARGET_SAMPLE_RATE}, CH={TARGET_CHANNELS}")

            # Conceptual: Publish Track via SignalRequest if not already done
            if not self.active_audio_track_cid:
                self.active_audio_track_cid = f"track_tts_{os.urandom(4).hex()}" # Generate a unique client ID
                add_track_req = rtc_pb2.AddTrackRequest(
                    cid=self.active_audio_track_cid,
                    name="artex_agent_tts_output",
                    type=0, # AUDIO
                    source=2 # MICROPHONE (or a custom source if defined)
                )
                # This request needs to be sent via the _generate_signal_requests stream.
                # This requires _generate_signal_requests to be more dynamic (e.g., using an asyncio.Queue)
                # For this PoC, we'll just log the intent.
                print(f"LKPH ({self.participant_identity}): Would send AddTrackRequest for CID {self.active_audio_track_cid} via Signal stream (simulated).")
                # yield rtc_pb2.SignalRequest(add_track=add_track_req) # If _generate_signal_requests was designed for this

            # Conceptual: Stream PCM Data via SignalRequest (if protocol supports it) or WebRTC
            # LiveKit's primary mechanism for media is WebRTC. Direct gRPC streaming of raw audio frames
            # within the SignalRequest/Response is not the standard way for media plane.
            # This part is highly conceptual for a direct gRPC approach without WebRTC libraries.
            # The client SDKs (JS, mobile, Python server SDK's Room object) handle WebRTC.
            print(f"LKPH ({self.participant_identity}): Would stream {len(pcm_data)} bytes of PCM for track CID {self.active_audio_track_cid} (simulated).")
            # For actual streaming with WebRTC and AudioSource (if using livekit Python SDK participant features):
            # audio_source = AudioSource(TARGET_SAMPLE_RATE, TARGET_CHANNELS)
            # track = LocalAudioTrack.create_audio_track("agent-tts", audio_source)
            # await room.local_participant.publish_track(track)
            # for i in range(0, len(pcm_data), BYTES_PER_FRAME):
            #     frame_chunk = pcm_data[i:i+BYTES_PER_FRAME]
            #     # Ensure frame_chunk is exactly BYTES_PER_FRAME, pad if last one is smaller
            #     livekit_frame = livekit.AudioFrame(data=frame_chunk, sample_rate=TARGET_SAMPLE_RATE, ...)
            #     await audio_source.capture_frame(livekit_frame)
            #     await asyncio.sleep(FRAME_DURATION_MS / 1000.0)

        except FileNotFoundError:
            print(f"LKPH ({self.participant_identity}): ERROR - FFmpeg not found or MP3 file handling issue. Ensure FFmpeg is in PATH for pydub MP3 support.")
        except Exception as e:
            print(f"LKPH ({self.participant_identity}): Error processing or simulating audio publishing: {e}")


    async def handle_incoming_audio_stream(self, track_sid: str, audio_stream_iterator: AsyncGenerator[bytes, None]):
        print(f"LKPH ({self.participant_identity}): handle_incoming_audio_stream for {track_sid} (Placeholder)")
        await asyncio.sleep(0.1)

    async def disconnect(self):
        print(f"LKPH ({self.participant_identity}): Disconnecting...")
        self._is_disconnected_event.set()
        if self.event_loop_task:
            if not self.event_loop_task.done(): self.event_loop_task.cancel()
            try: await self.event_loop_task
            except asyncio.CancelledError: print(f"LKPH ({self.participant_identity}): Event loop task cancelled.")
            except Exception as e: print(f"LKPH ({self.participant_identity}): Exception awaiting event_loop_task: {e}")
            self.event_loop_task = None
        if self.channel:
            await self.channel.close()
            print(f"LKPH ({self.participant_identity}): gRPC Channel closed.")
        self.channel = None; self.rtc_stub = None
        print(f"LKPH ({self.participant_identity}): Disconnected.")

async def main_test_participant_handler():
    from dotenv import load_dotenv
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    if not os.path.exists(dotenv_path): dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path): load_dotenv(dotenv_path=dotenv_path); print(f"Test: Loaded .env from {dotenv_path}")
    else: print(f"Test: .env file not found. Relying on env vars.")

    lk_url = os.getenv("LIVEKIT_URL")
    lk_api_key = os.getenv("LIVEKIT_API_KEY")
    lk_api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not all([lk_url, lk_api_key, lk_api_secret]):
        print("LIVEKIT_URL, API_KEY, or API_SECRET not set. Skipping full test."); return

    test_room = "arthextest_participant_handler"
    test_identity = f"agent_ph_tester_{os.urandom(3).hex()}"

    from livekit import AccessToken, VideoGrant # For generating a token for the test
    grant = VideoGrant(room_join=True, room=test_room, can_publish=True, can_subscribe=True)
    token_obj = AccessToken(lk_api_key, lk_api_secret, identity=test_identity, ttl=300, name="TestParticipantHandler") # 5 min TTL
    token_obj.grants = grant
    test_token = token_obj.to_jwt()
    print(f"Test: Generated token for identity '{test_identity}' in room '{test_room}'.")

    # Initialize TTSService for the handler
    try:
        tts_service_instance = TTSService()
        if not tts_service_instance: raise ValueError("TTS Service failed to init")
    except Exception as e:
        print(f"Test: Failed to initialize TTSService for handler: {e}"); return

    handler = LiveKitParticipantHandler(
        livekit_ws_url=lk_url,
        token=test_token,
        room_name=test_room,
        participant_identity=test_identity,
        tts_service=tts_service_instance
    )

    if await handler.connect():
        print("Test: Participant handler connect reported success.")
        await asyncio.sleep(2) # Let event loop run to simulate join confirmation

        await handler.publish_tts_audio_to_room("Bonjour, ceci est un test audio de l'agent Arthex via LiveKit et gRPC.")
        await asyncio.sleep(1) # Give time for logs if any

        await handler.disconnect()
    else:
        print("Test: Participant handler connect failed.")

if __name__ == "__main__":
    asyncio.run(main_test_participant_handler())
