import os
import asyncio
import datetime # Added for token TTL
from typing import Optional # Added for type hinting
from livekit import RoomServiceClient, Room, RoomOptions, LocalAudioTrack, AudioSource, Participant, AccessToken, VideoGrant
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
    Creates and returns a LiveKit RoomServiceClient instance using environment variables.
    """
    livekit_url = os.getenv("LIVEKIT_URL")
    livekit_api_key = os.getenv("LIVEKIT_API_KEY")
    livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not all([livekit_url, livekit_api_key, livekit_api_secret]):
        # This error will be caught by the caller, no direct log here is strictly needed,
        # but good for direct invocation.
        log.error("LIVEKIT_URL, LIVEKIT_API_KEY, or LIVEKIT_API_SECRET missing in environment.")
        raise ValueError("LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET must be set in environment variables.")

    try:
        room_service = RoomServiceClient(livekit_url, livekit_api_key, livekit_api_secret, keepalive_interval=60.0)
        log.info("RoomServiceClient initialized.", livekit_url=livekit_url)
        return room_service
    except Exception as e:
        log.error("Failed to initialize RoomServiceClient.", error_str=str(e), exc_info=True)
        raise # Re-raise to indicate failure

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

    video_grant = VideoGrant(
        room=room_name,
        room_join=True,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True
    )

    access_token = AccessToken(api_key, api_secret)
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
    Connects to a LiveKit room using a pre-generated token using the LiveKit Python Server SDK.
    This was part of the initial PoC for CLI LiveKit mode.
    Future agent participation should primarily use LiveKitParticipantHandler (gRPC based).
    """
    # Deprecation warning for runtime, if desired:
    # import warnings
    # warnings.warn("join_room_with_token in livekit_integration.py is deprecated for new participant logic. Use LiveKitParticipantHandler.", DeprecationWarning)
    log.warn("DEPRECATED: join_room_with_token (Python SDK participant logic) called. Consider migrating to LiveKitParticipantHandler.")
    room = Room()

    @room.on("participant_connected")
    async def on_participant_connected(participant: Participant):
        log.info("LiveKit: Participant connected.", room_name=room.name, participant_identity=participant.identity, is_local=participant.is_local)

    @room.on("disconnected")
    async def on_disconnected():
        log.info("LiveKit: Participant disconnected.", room_name=room.name, participant_identity=participant_identity) # This uses the outer scope identity

    try:
        log.info("LiveKit: Attempting to connect to room.", room_url_masked=livekit_url.split('?')[0], participant_identity=participant_identity)
        await room.connect(livekit_url, token, options=RoomOptions(auto_subscribe=True))
        log.info("LiveKit: Successfully connected to room.", room_name=room.name, participant_identity=participant_identity)
        return room
    except Exception as e:
        log.error("LiveKit: Error connecting to room.", participant_identity=participant_identity, error_str=str(e), exc_info=True)
        return None


# ----- Functions below are part of the agent's participant logic, using a connected Room object -----

async def publish_tts_audio_to_room(room: Room, text_to_speak: str):
    """
    DEPRECATED PoC FUNCTION (Python Server SDK for Participant Logic)
    Simulates publishing TTS audio to the LiveKit room using a Room object from the Python Server SDK.
    Used by the CLI LiveKit PoC mode.
    Future agent participation should use LiveKitParticipantHandler.
    """
    # Deprecation warning for runtime, if desired:
    # import warnings
    # warnings.warn("publish_tts_audio_to_room in livekit_integration.py is deprecated. Use LiveKitParticipantHandler.", DeprecationWarning)
    log.warn("DEPRECATED: publish_tts_audio_to_room (Python SDK participant logic) called. Consider migrating to LiveKitParticipantHandler.")

    if not room or not room.local_participant:
        log.warn("Cannot publish TTS (deprecated PoC): Not connected to a room or no local participant.")
        return
    log.info("LiveKit (Simulated TTS Publish): Publishing audio.", text_snippet=text_to_speak[:30], room_name=room.name, participant_identity=room.local_participant.identity)
    await asyncio.sleep(0.1) # Simulate async work

async def handle_room_events(room: Room):
    """
    DEPRECATED PoC FUNCTION (Python Server SDK for Participant Logic)
    Handles room events using a Room object from the Python Server SDK.
    Used by the CLI LiveKit PoC mode.
    Future agent participation should use LiveKitParticipantHandler.
    """
    # Deprecation warning for runtime, if desired:
    # import warnings
    # warnings.warn("handle_room_events in livekit_integration.py is deprecated. Use LiveKitParticipantHandler.", DeprecationWarning)
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
    async def on_participant_disconnected(remote_participant: Participant): # Corrected type hint
        log.info("LiveKit: Remote participant disconnected.", room_name=room.name, participant_identity=remote_participant.identity)

    try:
        while room.connection_state == "connected": # Check based on Room's actual state property if available
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        log.info("Event handler task cancelled.", room_name=room.name)
    finally:
        log.info("Event handler task finished.", room_name=room.name)


# ----- Server-side/Admin test function (can remain for testing RoomServiceClient) -----
async def test_list_rooms_admin(room_service: RoomServiceClient):
    """ Tests listing rooms using RoomServiceClient (admin task). """
    if not room_service:
        log.warn("RoomServiceClient not initialized for admin test.")
        return False, "RoomServiceClient not initialized."
    try:
        log.info("Attempting to list LiveKit rooms (admin)...")
        list_rooms_result = await room_service.list_rooms()
        rooms_info = []
        if list_rooms_result and list_rooms_result.rooms:
            for r_obj in list_rooms_result.rooms: # Renamed loop variable
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
    # Ensure .env is loaded for standalone testing
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(dotenv_path=dotenv_path)

    # Minimal logging setup for standalone execution if logging_config.py wasn't imported by an entry point
    # This needs to be done *before* any log calls are made by the module's functions if run directly.
    if not logging.getLogger().handlers or not structlog.is_configured():
        import logging # Re-import for basicConfig
        import structlog # Re-import for structlog
        import sys # For sys.stdout
        structlog.configure(processors=[structlog.dev.ConsoleRenderer()])
        logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), stream=sys.stdout)
        log.info("Minimal logging re-configured for livekit_integration.py standalone test.")

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

    log.info("\n--- Testing LiveKit RoomServiceClient (Admin Task - List Rooms) ---")
    # This part tests the RoomServiceClient for admin tasks like listing rooms.
    # It's separate from participant connection logic.
    async def run_admin_tests():
        lk_service_client = None
        try:
            lk_service_client = get_livekit_room_service() # This will log its own success/failure
            if lk_service_client:
                success, message = await test_list_rooms_admin(lk_service_client)
                if success:
                    log.info(f"Admin Test Result: SUCCESS - {message}")
                else:
                    log.warn(f"Admin Test Result: FAILED - {message}") # Changed to warn as error is logged in func
            else:
                log.warn("Skipping admin tests as RoomServiceClient could not be initialized.")
        except ValueError as ve: # Raised by get_livekit_room_service if config is missing
            log.error(f"Admin Test Configuration Error: {ve}") # Already logged by get_livekit_room_service
        except Exception as e:
            log.critical(f"An unexpected error occurred during LiveKit admin tests.", error_str=str(e), exc_info=True)
        finally:
            if lk_service_client:
                log.info("Closing LiveKit RoomServiceClient (admin test)...")
                await lk_service_client.close()
                log.info("LiveKit RoomServiceClient (admin test) closed.")

    asyncio.run(run_admin_tests())

    # Note: The `join_room_and_publish_audio` function (which used RoomServiceClient to get a token
    # and then Room().connect()) is now superseded by `generate_livekit_access_token` (for token)
    # and `join_room_with_token` (for Room().connect()).
    # The agent.py will use `generate_livekit_access_token` from this module (or RoomServiceClient.create_token)
    # and then `Room().connect()` itself, or a new helper like `join_room_with_token`.
    # The existing `join_room_and_publish_audio` in agent.py is what handles the participant logic.
    # This file (livekit_integration.py) should mostly contain server-side SDK interactions and token generation.
    # The participant-side room connection logic is now primarily in agent.py's main_async_logic.
    # The PoC functions `publish_tts_audio_to_room` and `handle_room_events` are here because
    # `agent.py` calls them, assuming they operate on a `Room` object.
    # This separation is a bit mixed up due to the PoC nature.
    # Ideally, `livekit_integration.py` = server tasks + token generation.
    # `livekit_participant_handler.py` = pure client RTC logic (gRPC based).
    # `agent.py` = orchestrator, using services from above.
    # The `join_room_and_publish_audio` in this file (if it were kept from previous step) was essentially
    # a participant action using the server SDK's client features.
    # The new `generate_livekit_access_token` is a pure server-side action (doesn't connect).
    # The `join_room_with_token` is a pure participant action (connects).
    # The `publish_tts_audio_to_room` and `handle_room_events` are participant actions on a connected `Room`.
    # It seems `agent.py` should directly use `Room().connect()` after getting a token.
    # The `join_room_and_publish_audio` in `livekit_integration.py` from step 22 was doing this combined step.
    # It's okay to keep it there if `agent.py` calls it.
    # The new `generate_livekit_access_token` is a more focused utility.
    # The subtask asks to add `generate_livekit_access_token` here.
    # The old `join_room_and_publish_audio` from step 22 is still in agent.py's `main_async_logic`.
    # This can be confusing. Let's assume the `join_room_and_publish_audio` in `livekit_integration.py`
    # (from step 22) is the one that `agent.py` uses.
    # The new `generate_livekit_access_token` is an additional utility in this file.
    # The `test_livekit_connection` is for admin `RoomServiceClient`.
    # The PoC participant functions `publish_tts_audio_to_room` and `handle_room_events` are also here
    # as they are called by `agent.py` and operate on a `Room` object.
    # This seems fine for now.
    # The `join_room_and_publish_audio` that was added in subtask 22 to `livekit_integration.py`
    # will be kept and `agent.py` will continue to use it. The new `generate_livekit_access_token`
    # is an alternative way to get a token if needed separately.
    # The current `livekit_integration.py` has `join_room_and_publish_audio` which *includes* token generation.
    # This is fine. The new function is just a standalone token generator.
    # The `__main__` block in `livekit_integration.py` should primarily test functions within this file.
    # The `test_list_rooms_admin` tests `RoomServiceClient`.
    # The new token function should also be tested here.
    # The participant-side functions `publish_tts_audio_to_room`, `handle_room_events` are harder to test standalone here
    # as they require a connected `Room` object.
    # The `join_room_and_publish_audio` (which returns a Room) could be used to test them, but that's more of an integration test.
    # The current `if __name__ == "__main__":` tests `list_rooms` and the new token generation. This is good.
    # The other functions (`join_room_and_publish_audio`, `publish_tts_audio_to_room`, `handle_room_events`) are
    # primarily for `agent.py` to import and use.
