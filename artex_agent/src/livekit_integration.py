import os
import asyncio
from livekit import RoomServiceClient, Room, RoomOptions, LocalAudioTrack, AudioSource, Participant # Added imports
from livekit.protocol import room_service as proto_room_service # For CreateRoomRequest
from livekit.grants import VideoGrant # For token generation
from dotenv import load_dotenv

# For PoC, we'll simulate audio frames. In reality, this needs proper audio handling.
# Placeholder for audio parameters - these would come from your actual audio source/format
SAMPLE_RATE = 48000
NUM_CHANNELS = 1
FRAME_DURATION_MS = 20 # 20ms frames
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

    # The RoomServiceClient takes the URL, API key, and API secret upon initialization.
    # Ensure keepalive_interval is set if you expect long-lived clients not actively making requests
    room_service = RoomServiceClient(livekit_url, livekit_api_key, livekit_api_secret, keepalive_interval=60.0)
    return room_service

async def join_room_and_publish_audio(room_service: RoomServiceClient, room_name: str, participant_identity: str) -> Room | None:
    """
    Creates a room if it doesn't exist, generates a token, connects to the room,
    and prepares for publishing audio.
    """
    if not room_service:
        print("LiveKit RoomServiceClient not provided.")
        return None

    print(f"Attempting to join room: {room_name} as {participant_identity}")

    # 1. Create room if it doesn't exist (optional, depends on your setup)
    # For this PoC, we assume the room might need to be created.
    # create_room_request = proto_room_service.CreateRoomRequest(name=room_name)
    # try:
    #     await room_service.create_room(create_room_request)
    #     print(f"Room '{room_name}' created or already existed.")
    # except Exception as e:
    #     # Handle cases where room already exists if create_room doesn't upsert
    #     print(f"Could not create room (it might already exist or an error occurred): {e}")
    #     # Depending on the error, you might want to proceed or return None

    # 2. Generate token
    # Token needs to grant publishing rights if the agent is to speak
    grant = VideoGrant(room_join=True, room=room_name, can_publish=True, can_subscribe=True) # Allow publishing and subscribing

    try:
        token_info = await room_service.create_token(identity=participant_identity, grant=grant)
        token = token_info.token
        print(f"Token generated for {participant_identity} to join {room_name}")
    except Exception as e:
        print(f"Error generating token: {e}")
        return None

    # 3. Create Room object and connect
    room = Room()

    # Event listener for when the local participant successfully joins the room
    @room.on("participant_connected")
    async def on_participant_connected(participant: Participant):
        print(f"Local participant {participant.identity} connected to room {room.name}")

    # Event listener for disconnection
    @room.on("disconnected")
    async def on_disconnected():
        print(f"Disconnected from room {room.name}")


    try:
        livekit_url = os.getenv("LIVEKIT_URL")
        if not livekit_url:
            raise ValueError("LIVEKIT_URL not found in environment variables for room connection.")

        print(f"Connecting to room {room_name} at {livekit_url}...")
        await room.connect(livekit_url, token, options=RoomOptions(auto_subscribe=True)) # Auto-subscribe to new tracks
        print(f"Successfully connected to room: {room.name} as {room.local_participant.identity}")
        return room
    except Exception as e:
        print(f"Error connecting to room {room_name}: {e}")
        return None

async def publish_tts_audio_to_room(room: Room, text_to_speak: str):
    """
    Placeholder for publishing TTS audio to the LiveKit room.
    Actual implementation requires gTTS -> audio frames -> LiveKit AudioSource.
    """
    if not room or not room.local_participant:
        print("Not connected to a room or no local participant.")
        return

    print(f"LiveKit (Simulated TTS Publish): Would publish audio for text: '{text_to_speak}' to room '{room.name}'")
    # --- Start of actual audio publishing (conceptual for now) ---
    # 1. Generate TTS audio bytes (e.g., gTTS to BytesIO)
    #    from io import BytesIO
    #    from gtts import gTTS
    #    mp3_fp = BytesIO()
    #    tts = gTTS(text=text_to_speak, lang='fr')
    #    tts.write_to_fp(mp3_fp)
    #    mp3_fp.seek(0)
    #    # mp3_bytes = mp3_fp.read() # This is MP3 data

    # 2. Convert MP3 bytes to raw PCM audio frames
    #    This is the complex step requiring pydub or ffmpeg.
    #    Example using pydub (requires ffmpeg installed):
    #    from pydub import AudioSegment
    #    audio_segment = AudioSegment.from_file(mp3_fp, format="mp3")
    #    # Resample to desired sample rate and channels for LiveKit
    #    audio_segment = audio_segment.set_frame_rate(SAMPLE_RATE).set_channels(NUM_CHANNELS)
    #    # pcm_frames = audio_segment.raw_data -> this is the raw PCM

    # 3. Create an AudioSource
    #    audio_source = AudioSource(SAMPLE_RATE, NUM_CHANNELS)

    # 4. Publish the track
    #    track = LocalAudioTrack.create_audio_track("agent-tts-output", audio_source)
    #    await room.local_participant.publish_track(track)
    #    print("Local audio track published.")

    # 5. Push frames to the source
    #    # Assume pcm_frames is available and correctly formatted
    #    # You'd need to chunk pcm_frames into appropriate frame sizes for LiveKit
    #    # For example, if LiveKit expects 20ms frames:
    #    bytes_per_sample = 2 # 16-bit PCM
    #    frame_size_in_bytes = SAMPLES_PER_FRAME * NUM_CHANNELS * bytes_per_sample
    #
    #    for i in range(0, len(pcm_frames), frame_size_in_bytes):
    #        chunk = pcm_frames[i:i+frame_size_in_bytes]
    #        if len(chunk) < frame_size_in_bytes:
    #            # Pad if necessary, or handle partial frame
    #            # For simplicity, we might just send it if it's the last one
    #            pass
    #        frame = AudioFrame(data=chunk, sample_rate=SAMPLE_RATE, num_channels=NUM_CHANNELS, samples_per_channel=SAMPLES_PER_FRAME)
    #        await audio_source.capture_frame(frame)
    #        await asyncio.sleep(0.018) # Approximate sleep for 20ms frame, adjust for processing time
    #
    #    print("Finished publishing TTS audio.")
    #    await room.local_participant.unpublish_track(track.sid) # Optionally unpublish after speaking
    # --- End of actual audio publishing ---
    await asyncio.sleep(0.1) # Simulate some async work

async def handle_room_events(room: Room):
    """
    Placeholder for handling room events, especially incoming audio tracks.
    """
    if not room:
        print("Room object not provided for event handling.")
        return

    print(f"Setting up event handlers for room: {room.name}")

    @room.on("track_subscribed")
    async def on_track_subscribed(track, publication, participant):
        print(f"Track subscribed: {track.sid} from participant {participant.identity} (name: {participant.name})")
        if track.kind == "audio":
            print(f"Subscribed to AUDIO track from {participant.identity}. PoC: Will not process frames.")
            # In a full implementation, you would do something like:
            # audio_stream = AudioStream(track)
            # async for frame_event in audio_stream:
            #     # frame_event.frame is an AudioFrame
            #     # This is where you'd buffer and send to STT
            #     pass
        elif track.kind == "video":
            print(f"Subscribed to VIDEO track from {participant.identity}. (Not handled by this agent)")

    @room.on("track_unsubscribed")
    async def on_track_unsubscribed(track, publication, participant):
        print(f"Track unsubscribed: {track.sid} from participant {participant.identity}")

    @room.on("participant_disconnected")
    async def on_participant_disconnected(participant: Participant):
        print(f"Participant {participant.identity} disconnected from room {room.name}.")

    # Keep this task alive to listen for events
    # In a real app, this might be part of a larger async task management system
    try:
        while room.connection_state == "connected": # Or some other condition
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        print("Event handler task cancelled.")
    finally:
        print("Event handler task finished.")


async def test_livekit_connection(room_service: RoomServiceClient):
    """
    Tests the LiveKit connection by attempting to list rooms.

    Args:
        room_service: An initialized LiveKit RoomServiceClient.

    Returns:
        A tuple (success: bool, message: str)
    """
    if not room_service:
        return False, "RoomServiceClient not initialized."

    try:
        print("Attempting to list LiveKit rooms...")
        list_rooms_result = await room_service.list_rooms()

        rooms_info = []
        if list_rooms_result and list_rooms_result.rooms:
            for room in list_rooms_result.rooms:
                rooms_info.append(f"Room SID: {room.sid}, Name: {room.name}, Num Participants: {room.num_participants}")
            rooms_str = "\n".join(rooms_info)
            return True, f"LiveKit connection successful. Rooms found:\n{rooms_str}"
        else:
            return True, "LiveKit connection successful. No active rooms found."

    except Exception as e:
        return False, f"LiveKit connection test failed: {e}"

if __name__ == "__main__":
    print("Testing LiveKit connection...")
    load_dotenv() # Ensure .env variables are loaded

    service_client = None
    try:
        service_client = get_livekit_room_service()
        print(f"LiveKit RoomServiceClient initialized for URL: {os.getenv('LIVEKIT_URL')}")

        success, message = asyncio.run(test_livekit_connection(service_client))

        if success:
            print(f"Test Result: SUCCESS - {message}")
        else:
            print(f"Test Result: FAILED - {message}")

    except ValueError as ve:
        print(f"Configuration Error: {ve}")
    except Exception as e:
        print(f"An unexpected error occurred during LiveKit test: {e}")
    finally:
        if service_client:
            # The RoomServiceClient in the Python SDK typically uses an HTTP client (like httpx) internally.
            # Proper cleanup involves closing this client.
            # The SDK's RoomServiceClient has an `close()` async method.
            print("Closing LiveKit service client...")
            async def close_client():
                await service_client.close()
            asyncio.run(close_client())
            print("LiveKit service client closed.")
