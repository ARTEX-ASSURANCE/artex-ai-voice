# Placeholder for livekit_rtc_pb2.py
# Enhanced to better support LiveKitParticipantHandler structure

from typing import List, Optional # Added for type hints in dummy classes

# --- Message Types (Simplified Examples) ---

class Room:
    def __init__(self, name="default_room_name", sid="RM_default_sid", metadata="", empty_timeout=0, max_participants=0, creation_time=0, turn_password="", enabled_codecs=None, active_recording=False, num_participants=0, num_publishers=0, version=0):
        self.name = name
        self.sid = sid
        self.metadata = metadata
        pass

class ParticipantInfo:
    def __init__(self, sid="PA_default_sid", identity="default_identity", name="Default Name", metadata="", state=0, is_speaking=False): # state e.g. JOINED, ACTIVE, DISCONNECTED
        self.sid = sid
        self.identity = identity
        self.name = name
        self.metadata = metadata
        self.state = state
        self.is_speaking = is_speaking
        pass

class TrackInfo:
    def __init__(self, sid="TR_default_sid", name="default_track_name", type=0, muted=False, source=0, participant_sid="PA_default_sid"): # type 0 for AUDIO (TrackType enum in real proto)
        self.sid = sid
        self.name = name
        self.type = type
        self.muted = muted
        self.source = source
        self.participant_sid = participant_sid # Added for context
        pass

class JoinRequest:
    def __init__(self, room_name: str, identity: str, token: str, options: Optional[dict] = None):
        self.room_name = room_name
        self.identity = identity
        self.token = token
        self.options = options if options else {}
        pass

class JoinResponse:
    def __init__(self, room: Optional[Room] = None, participant: Optional[ParticipantInfo] = None, other_participants: Optional[List[ParticipantInfo]] = None, server_version: str = "0.0.0", ice_servers: Optional[List[dict]] = None):
        self.room = room if room else Room()
        self.participant = participant if participant else ParticipantInfo()
        self.other_participants = other_participants if other_participants else []
        self.server_version = server_version
        self.ice_servers = ice_servers if ice_servers else []
        pass

class ParticipantUpdate:
     def __init__(self, participants: Optional[List[ParticipantInfo]] = None):
        self.participants = participants if participants else []
        pass

class TrackPublishedResponse:
     def __init__(self, participant_sid: str = "", track: Optional[TrackInfo] = None): # Simplified: track is TrackInfo
        self.participant_sid = participant_sid
        self.track = track if track else TrackInfo(sid="TR_pub_default") # Ensure track is an object
        pass

class SpeakerInfo:
    def __init__(self, sid: str = "", level: float = 0.0, active: bool = False):
        self.sid = sid
        self.level = level
        self.active = active
        pass

class SpeakersChanged:
    def __init__(self, speakers: Optional[List[SpeakerInfo]] = None):
        self.speakers = speakers if speakers else []
        pass

class LeaveRequest:
    def __init__(self, can_reconnect: bool = False, reason: int = 0):
        self.can_reconnect = can_reconnect
        self.reason = reason
        pass

class LeaveResponse:
    def __init__(self, can_reconnect: bool = False, reason: int = 0):
        self.can_reconnect = can_reconnect
        self.reason = reason
        pass

# --- Messages for Track Publishing (Client to Server) ---
class AddTrackRequest:
    def __init__(self, cid: str = "default_cid", name: str = "default_track", type: int = 0, source: int = 2, # AUDIO, MICROPHONE
                 width: int = 0, height: int = 0, mute: bool = False, disable_dtx: bool = False,
                 encryption: int = 0, layers=None, simulcast_codecs=None, sid: str = ""):
        self.cid = cid
        self.name = name
        self.type = type
        self.source = source
        self.width = width
        self.height = height
        self.mute = mute
        self.disable_dtx = disable_dtx
        self.encryption = encryption
        self.layers = layers if layers else []
        self.simulcast_codecs = simulcast_codecs if simulcast_codecs else []
        self.sid = sid
        pass

class AudioFrame: # For streaming audio data via WebRTC or potentially a gRPC stream if supported
    def __init__(self, data: bytes = b"", timestamp_us: int = 0, num_channels: int = 1, sample_rate: int = 48000):
        self.data = data
        self.timestamp_us = timestamp_us
        self.num_channels = num_channels
        self.sample_rate = sample_rate
        pass

class SignalRequest:
    def __init__(self, join: Optional[JoinRequest] = None, offer=None, answer=None, trickle=None,
                 add_track: Optional[AddTrackRequest] = None,
                 mute=None, subscription=None, track_setting=None, leave: Optional[LeaveRequest] = None,
                 update_layers=None, subscription_permission=None, sync_state=None,
                 simulate_scenario=None, ping_req=None, update_participant_metadata=None):
        self.join = join
        self.offer = offer
        self.answer = answer
        self.trickle = trickle
        self.add_track = add_track
        self.mute = mute
        self.subscription = subscription
        self.track_setting = track_setting
        self.leave = leave
        pass

    def SerializeToString(self):
        if self.join: return b"join_request_simulated_data_with_token"
        if self.leave: return b"leave_request_simulated_data"
        if self.add_track: return b"add_track_request_simulated_data"
        return b"dummy_signal_request_data"

class SignalResponse:
    def __init__(self, join: Optional[JoinResponse] = None, answer=None, offer=None, trickle=None, update=None,
                 track_published: Optional[TrackPublishedResponse] = None,
                 participant_update: Optional[ParticipantUpdate] = None,
                 speakers_changed: Optional[SpeakersChanged] = None,
                 room_update=None, connection_quality=None,
                 leave: Optional[LeaveResponse] = None,
                 mute=None, stream_state_update=None, subscribed_quality_update=None,
                 subscription_permission_update=None, pong_resp=None, reconnect=None,
                 subscription_response=None):
        self.join = join
        self.answer = answer
        self.offer = offer
        self.trickle = trickle
        self.update = update
        self.track_published = track_published
        self.participant_update = participant_update
        self.speakers_changed = speakers_changed
        self.room_update = room_update
        self.connection_quality = connection_quality
        self.leave = leave
        pass

    @classmethod
    def FromString(cls, value_bytes: bytes):
        # Mock parser for testing the event loop.
        if value_bytes == b"simulate_join_response":
            return cls(join=JoinResponse(room=Room(name="test-room-from-sim-grpc", sid="RM_SIM"),
                                         participant=ParticipantInfo(sid="PA_SIM_LOCAL", identity="agent-sim")))
        elif value_bytes == b"simulate_participant_join_event":
            return cls(participant_update=ParticipantUpdate(participants=[ParticipantInfo(sid="PA_SIM_OTHER", identity="user123", name="User 123", state=1)]))
        elif value_bytes == b"simulate_track_published_event":
            return cls(track_published=TrackPublishedResponse(participant_sid="PA_SIM_OTHER", track=TrackInfo(sid="TR_audio_sim", name="audio", type=0)))
        elif value_bytes == b"simulate_speakers_changed_event":
            return cls(speakers_changed=SpeakersChanged(speakers=[SpeakerInfo(sid="PA_SIM_OTHER", level=0.8, active=True)]))
        elif value_bytes == b"simulate_leave_response":
            return cls(leave=LeaveResponse())
        return cls()

print("Placeholder livekit_rtc_pb2.py loaded (enhanced with AddTrackRequest, AudioFrame).")
