This directory is intended to hold Python gRPC stubs generated from LiveKit's .proto files for its Real-time Communication (RTC) services. These stubs are necessary if the agent needs to interact with LiveKit's RTC layer directly using gRPC, for functionalities like publishing or subscribing to media tracks as a participant, beyond what the server-side `livekit` SDK (RoomServiceClient) typically handles.

Acquiring Proto Files:
LiveKit's protocol definition files (e.g., `livekit_rtc.proto`, `livekit_models.proto`, `livekit_room.proto`, `livekit_egress.proto`, `livekit_ingress.proto`) can usually be found in the official LiveKit protocol repository or within the main LiveKit server repository (e.g., under a `protocol` or `protos` directory).
Example GitHub repository: https://github.com/livekit/protocol

Generating Python Stubs:
Once you have the .proto files (e.g., in a local directory named `protos/livekit`), you can generate the Python gRPC stubs using `grpc_tools.protoc`. The command typically looks like this:

```bash
# Ensure grpcio-tools is installed: pip install grpcio-tools protobuf

# Example command (adjust paths and proto file names as needed):
python -m grpc_tools.protoc \
    -I./path/to/your/protos/dir \
    --python_out=./artex_agent/src/livekit_rtc_stubs \
    --pyi_out=./artex_agent/src/livekit_rtc_stubs \
    --grpc_python_out=./artex_agent/src/livekit_rtc_stubs \
    ./path/to/your/protos/dir/livekit_*.proto
    # You might need to list individual .proto files if wildcard doesn't work or includes unwanted files.
    # e.g., ./path/to/your/protos/dir/livekit_rtc.proto ./path/to/your/protos/dir/livekit_models.proto etc.
```

Explanation of Command Options:
- `-I./path/to/your/protos/dir`: Specifies the directory where your .proto files (and any imported .proto files) are located.
- `--python_out=./artex_agent/src/livekit_rtc_stubs`: Specifies the output directory for the generated `_pb2.py` files (message classes).
- `--pyi_out=./artex_agent/src/livekit_rtc_stubs`: Specifies the output directory for the generated `_pb2.pyi` files (type stubs).
- `--grpc_python_out=./artex_agent/src/livekit_rtc_stubs`: Specifies the output directory for the generated `_pb2_grpc.py` files (service stubs and clients).
- The final arguments are the paths to the .proto files to be compiled.

After generation, this directory should contain files like `livekit_rtc_pb2.py`, `livekit_rtc_pb2_grpc.py`, `livekit_models_pb2.py`, etc. These can then be imported and used by `LiveKitParticipantHandler` or other client-side RTC logic.

Note: The exact set of .proto files and their interdependencies can be found in the LiveKit protocol documentation. Ensure all necessary .proto files are downloaded and paths are correct for generation.
The `livekit` Python SDK (server-sdk) primarily provides `RoomServiceClient` for administrative tasks and does not typically include the client-side RTC gRPC stubs for direct participant media handling; those are usually part of client SDKs (JS, mobile, etc.) or would be generated as described if building a custom Python RTC client.
