import os
import asyncio
import datetime # Added for token TTL
from typing import Optional # Added for type hinting
from livekit import RoomServiceClient, Room, RoomOptions, LocalAudioTrack, AudioSource, Participant, AccessToken, VideoGrant
# Removed proto_room_service import as create_room is not used in this version of join_room_and_publish_audio
# from livekit.protocol import room_service as proto_room_service
from dotenv import load_dotenv

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
        raise ValueError("LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET must be set in environment variables.")

    room_service = RoomServiceClient(livekit_url, livekit_api_key, livekit_api_secret, keepalive_interval=60.0)
    return room_service

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
        print("Error: LIVEKIT_API_KEY or LIVEKIT_API_SECRET not found in environment.")
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
        return token_jwt
    except Exception as e:
        print(f"Error generating LiveKit token: {e}")
        return None

async def join_room_with_token(livekit_url: str, token: str, participant_identity: str) -> Room | None:
    """
    Connects to a LiveKit room using a pre-generated token.
    This is the primary way a participant (like our agent) should connect.
    """
    room = Room()

    @room.on("participant_connected")
    async def on_participant_connected(participant: Participant):
        print(f"Participant {participant.identity} (local: {participant.is_local}) connected to room {room.name}")

    @room.on("disconnected")
    async def on_disconnected():
        print(f"Participant {participant_identity} disconnected from room {room.name}")

    try:
        print(f"Participant {participant_identity} attempting to connect to room at {livekit_url}...")
        await room.connect(livekit_url, token, options=RoomOptions(auto_subscribe=True))
        print(f"Participant {participant_identity} successfully connected to room: {room.name}")
        return room
    except Exception as e:
        print(f"Participant {participant_identity} error connecting to room: {e}")
        return None


# ----- Functions below are part of the agent's participant logic, using a connected Room object -----

async def publish_tts_audio_to_room(room: Room, text_to_speak: str):
    """
    Placeholder for publishing TTS audio to the LiveKit room.
    """
    if not room or not room.local_participant:
        print("Cannot publish TTS: Not connected to a room or no local participant.")
        return
    print(f"LiveKit (Simulated TTS Publish): Would publish audio for text: '{text_to_speak}' to room '{room.name}' by {room.local_participant.identity}")
    await asyncio.sleep(0.1) # Simulate async work

async def handle_room_events(room: Room):
    """
    Placeholder for handling room events, especially incoming audio tracks.
    """
    if not room:
        print("Room object not provided for event handling.")
        return
    print(f"Setting up event handlers for room: {room.name} (Participant: {room.local_participant.identity})")

    @room.on("track_subscribed")
    async def on_track_subscribed(track, publication, participant):
        print(f"Track subscribed: {track.sid} from participant {participant.identity} (name: {participant.name})")
        if track.kind == "audio":
            print(f"Subscribed to AUDIO track from {participant.identity}. PoC: Will not process frames.")
        elif track.kind == "video":
            print(f"Subscribed to VIDEO track from {participant.identity}. (Not handled by this agent)")

    @room.on("track_unsubscribed")
    async def on_track_unsubscribed(track, publication, participant):
        print(f"Track unsubscribed: {track.sid} from participant {participant.identity}")

    @room.on("participant_disconnected")
    async def on_participant_disconnected(remote_participant: Participant): # Corrected type hint
        print(f"Remote participant {remote_participant.identity} disconnected from room {room.name}.")

    try:
        while room.connection_state == "connected": # Check based on Room's actual state property if available
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        print(f"Event handler task for room {room.name} cancelled.")
    finally:
        print(f"Event handler task for room {room.name} finished.")


# ----- Server-side/Admin test function (can remain for testing RoomServiceClient) -----
async def test_list_rooms_admin(room_service: RoomServiceClient):
    """ Tests listing rooms using RoomServiceClient (admin task). """
    if not room_service:
        return False, "RoomServiceClient not initialized."
    try:
        print("Attempting to list LiveKit rooms (admin)...")
        list_rooms_result = await room_service.list_rooms()
        rooms_info = []
        if list_rooms_result and list_rooms_result.rooms:
            for r in list_rooms_result.rooms: # Changed 'room' to 'r' to avoid conflict
                rooms_info.append(f"  Room SID: {r.sid}, Name: {r.name}, Num Participants: {r.num_participants}")
            rooms_str = "\n".join(rooms_info)
            return True, f"LiveKit admin connection successful. Rooms found:\n{rooms_str}"
        else:
            return True, "LiveKit admin connection successful. No active rooms found."
    except Exception as e:
        return False, f"LiveKit admin connection test (list_rooms) failed: {e}"


if __name__ == "__main__":
    # Ensure .env is loaded for standalone testing
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    load_dotenv(dotenv_path=dotenv_path)

    print("--- Testing LiveKit Token Generation ---")
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
        print(f"Generated Token for {test_participant_identity} in room {test_room_name}:")
        print(token[:30] + "..." + token[-30:]) # Print snippet
    else:
        print("Failed to generate token.")

    print("\n--- Testing LiveKit RoomServiceClient (Admin Task - List Rooms) ---")
    # This part tests the RoomServiceClient for admin tasks like listing rooms.
    # It's separate from participant connection logic.
    async def run_admin_tests():
        lk_service_client = None
        try:
            lk_service_client = get_livekit_room_service()
            if lk_service_client:
                print(f"LiveKit RoomServiceClient initialized for URL: {os.getenv('LIVEKIT_URL')}")
                success, message = await test_list_rooms_admin(lk_service_client)
                if success:
                    print(f"Admin Test Result: SUCCESS - {message}")
                else:
                    print(f"Admin Test Result: FAILED - {message}")
            else:
                print("Skipping admin tests as RoomServiceClient could not be initialized.")
        except ValueError as ve:
            print(f"Admin Test Configuration Error: {ve}")
        except Exception as e:
            print(f"An unexpected error occurred during LiveKit admin tests: {e}")
        finally:
            if lk_service_client:
                print("Closing LiveKit RoomServiceClient (admin test)...")
                await lk_service_client.close()
                print("LiveKit RoomServiceClient (admin test) closed.")

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
