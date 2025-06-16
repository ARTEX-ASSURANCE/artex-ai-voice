import os
import asyncio
import datetime # Added for token TTL
from typing import Optional # Added for type hinting

from livekit import api # For server-side API access
from livekit import Room, RoomOptions, LocalAudioTrack, AudioSource, Participant # For client PoC parts

# Removed proto_room_service import as create_room is not used in this version of join_room_and_publish_audio
# from livekit.protocol import room_service as proto_room_service
from dotenv import load_dotenv

# Import logging configuration
from .logging_config import get_logger
log = get_logger(__name__)

# For PoC, we'll simulate audio frames. In reality, this needs proper audio handling.
SAMPLE_RATE = 48000
NUM_CHANNELS = 1
FRAME_DURATION_MS = 20
SAMPLES_PER_FRAME = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)

def get_livekit_room_service():
    """
    Creates and returns a LiveKit RoomService client instance using environment variables.
    """
    livekit_url = os.getenv("LIVEKIT_URL")
    livekit_api_key = os.getenv("LIVEKIT_API_KEY")
    livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not all([livekit_url, livekit_api_key, livekit_api_secret]):
        log.error("LIVEKIT_URL, LIVEKIT_API_KEY, or LIVEKIT_API_SECRET missing in environment.")
        raise ValueError("LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET must be set in environment variables.")

    transformed_url = livekit_url
    if livekit_url.startswith("wss://"):
        transformed_url = "https://" + livekit_url[6:]
    elif livekit_url.startswith("ws://"):
        transformed_url = "http://" + livekit_url[5:]

    try:
        lk_api = api.LiveKitAPI(
            url=transformed_url,
            api_key=livekit_api_key,
            api_secret=livekit_api_secret
        )
        log.info("LiveKitAPI client initialized using livekit.api.", livekit_api_url=transformed_url)
        return lk_api.room # This is the RoomService client
    except Exception as e:
        log.error("Failed to initialize LiveKitAPI client using livekit.api.", error_str=str(e), exc_info=True)
        raise

def generate_livekit_access_token(
        room_name: str,
        participant_identity: str,
        participant_name: Optional[str] = None,
        participant_metadata: Optional[str] = None,
        ttl_hours: int = 1
    ) -> Optional[str]:

    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        log.error("LIVEKIT_API_KEY or LIVEKIT_API_SECRET not found for token generation.")
        return None

    video_grant = api.VideoGrant( # Using api.VideoGrant
        room=room_name,
        room_join=True,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True
    )

    access_token = api.AccessToken(api_key, api_secret) # Using api.AccessToken
    access_token.identity = participant_identity
    if participant_name:
        access_token.name = participant_name
    if participant_metadata:
        access_token.metadata = participant_metadata

    access_token.grants = video_grant
    access_token.ttl = datetime.timedelta(hours=ttl_hours)

    try:
        token_jwt = access_token.to_jwt()
        log.info("LiveKit access token generated.", identity=participant_identity, room_name=room_name)
        return token_jwt
    except Exception as e:
        log.error("Error generating LiveKit token.", error_str=str(e), exc_info=True)
        return None

async def join_room_with_token(livekit_url: str, token: str, participant_identity: str) -> Room | None:
    """
    DEPRECATED PoC FUNCTION (Python Server SDK for Participant Logic)
    """
    log.warn("DEPRECATED: join_room_with_token (Python SDK participant logic) called. Consider migrating to LiveKitParticipantHandler.")
    room = Room()

    @room.on("participant_connected")
    async def on_participant_connected(participant: Participant):
        log.info("LiveKit: Participant connected.", room_name=room.name, participant_identity=participant.identity, is_local=participant.is_local)

    @room.on("disconnected")
    async def on_disconnected():
        log.info("LiveKit: Participant disconnected.", room_name=room.name, participant_identity=participant_identity)

    try:
        log.info("LiveKit: Attempting to connect to room.", room_url_masked=livekit_url.split('?')[0], participant_identity=participant_identity)
        await room.connect(livekit_url, token, options=RoomOptions(auto_subscribe=True))
        log.info("LiveKit: Successfully connected to room.", room_name=room.name, participant_identity=participant_identity)
        return room
    except Exception as e:
        log.error("LiveKit: Error connecting to room.", participant_identity=participant_identity, error_str=str(e), exc_info=True)
        return None

async def publish_tts_audio_to_room(room: Room, text_to_speak: str):
    """
    DEPRECATED PoC FUNCTION (Python Server SDK for Participant Logic)
    """
    log.warn("DEPRECATED: publish_tts_audio_to_room (Python SDK participant logic) called. Consider migrating to LiveKitParticipantHandler.")
    if not room or not room.local_participant:
        log.warn("Cannot publish TTS (deprecated PoC): Not connected to a room or no local participant.")
        return
    log.info("LiveKit (Simulated TTS Publish): Publishing audio.", text_snippet=text_to_speak[:30], room_name=room.name, participant_identity=room.local_participant.identity)
    await asyncio.sleep(0.1)

async def handle_room_events(room: Room):
    """
    DEPRECATED PoC FUNCTION (Python Server SDK for Participant Logic)
    """
    log.warn("DEPRECATED: handle_room_events (Python SDK participant logic) called. Consider migrating to LiveKitParticipantHandler.")
    if not room:
        log.warn("Room object not provided for event handling (deprecated PoC).")
        return
    log.info("Setting up event handlers for room.", room_name=room.name, participant_identity=(room.local_participant.identity if room.local_participant else "N/A"))

    @room.on("track_subscribed")
    async def on_track_subscribed(track, publication, participant):
        log.info("LiveKit: Track subscribed.", track_sid=track.sid, participant_identity=participant.identity, track_kind=track.kind)
        if track.kind == "audio":
            log.info("Subscribed to AUDIO track. PoC: Will not process frames.", track_sid=track.sid, participant_identity=participant.identity)
        elif track.kind == "video":
            log.info("Subscribed to VIDEO track (Not handled by this agent).", track_sid=track.sid, participant_identity=participant.identity)

    @room.on("track_unsubscribed")
    async def on_track_unsubscribed(track, publication, participant):
        log.info("LiveKit: Track unsubscribed.", track_sid=track.sid, participant_identity=participant.identity)

    @room.on("participant_disconnected")
    async def on_participant_disconnected(remote_participant: Participant):
        log.info("LiveKit: Remote participant disconnected.", room_name=room.name, participant_identity=remote_participant.identity)

    try:
        while room.connection_state == "connected":
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        log.info("Event handler task cancelled.", room_name=room.name)
    finally:
        log.info("Event handler task finished.", room_name=room.name)

async def test_list_rooms_admin(room_service: api.RoomService): # Updated type hint
    """ Tests listing rooms using RoomService (admin task). """
    if not room_service:
        log.warn("RoomService not initialized for admin test.")
        return False, "RoomService not initialized."
    try:
        log.info("Attempting to list LiveKit rooms (admin)...")
        list_rooms_result = await room_service.list_rooms()
        rooms_info = []
        if list_rooms_result and list_rooms_result.rooms:
            for r_obj in list_rooms_result.rooms:
                rooms_info.append(f"  Room SID: {r_obj.sid}, Name: {r_obj.name}, Num Participants: {r_obj.num_participants}")
            rooms_str = "\n".join(rooms_info)
            log.info("LiveKit admin: Rooms found.", num_rooms=len(rooms_info))
            return True, f"LiveKit admin connection successful. Rooms found:\n{rooms_str}"
        else:
            log.info("LiveKit admin: No active rooms found.")
            return True, "LiveKit admin connection successful. No active rooms found."
    except Exception as e:
        log.error("LiveKit admin connection test (list_rooms) failed.", error_str=str(e), exc_info=True)
        return False, f"LiveKit admin connection test (list_rooms) failed: {e}"

if __name__ == "__main__":
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(dotenv_path=dotenv_path)

    if not log.handlers or not getattr(log, 'is_configured', False):
        import logging
        import structlog
        import sys
        structlog.configure(
            processors=[
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.StackInfoRenderer(),
                structlog.dev.set_exc_info,
                structlog.dev.ConsoleRenderer(),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), stream=sys.stdout, format="%(message)s")
        log = get_logger(__name__)
        log.info("Minimal logging re-configured for livekit_integration.py standalone test (structlog).")

    log.info("--- Testing LiveKit Token Generation ---")
    test_room_name = "my-test-room-for-token"
    test_participant_identity = "artex-agent-token-tester"

    token = generate_livekit_access_token(
        room_name=test_room_name,
        participant_identity=test_participant_identity,
        participant_name="ArtexAgentTokenTester",
        participant_metadata='{"role": "ai_assistant_token_test"}',
        ttl_hours=1
    )

    if token:
        log.info(f"Generated Token for {test_participant_identity} in room {test_room_name}: {token[:30]}...{token[-30:]}")
    else:
        log.error("Failed to generate token in standalone test.")

    log.info("\n--- Testing LiveKit RoomService (Admin Task - List Rooms) ---")
    async def run_admin_tests():
        lk_service_client = None
        try:
            lk_service_client = get_livekit_room_service()
            if lk_service_client:
                success, message = await test_list_rooms_admin(lk_service_client)
                if success:
                    log.info(f"Admin Test Result: SUCCESS - {message}")
                else:
                    log.warn(f"Admin Test Result: FAILED - {message}")
            else:
                log.warn("Skipping admin tests as RoomService client could not be initialized.")
        except ValueError as ve:
            log.error(f"Admin Test Configuration Error: {ve}")
        except Exception as e:
            log.critical(f"An unexpected error occurred during LiveKit admin tests.", error_str=str(e), exc_info=True)

    asyncio.run(run_admin_tests())
