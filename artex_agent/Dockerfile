# Stage 1: Build/Dependency Stage
# Use a specific Python version, aligning with project requirements (e.g., 3.11 or 3.12)
# Slim variant is preferred for smaller image size.
FROM python:3.11-slim AS builder

WORKDIR /opt/venv
# Create a virtual environment
RUN python -m venv .
ENV PATH="/opt/venv/bin:$PATH" # Activate venv

# Install build tools if any C extensions need compilation (e.g., some older PyAudio wheels might)
# For PyAudio on Debian/Ubuntu based images (like python:slim which is Debian based):
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc build-essential libportaudio2 libportaudiocpp0 portaudio19-dev && \
    rm -rf /var/lib/apt/lists/*
# For ffmpeg (dependency for pydub for MP3 handling, if not statically linked or if full ffmpeg features are needed by pydub)
# RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
# Note: Installing ffmpeg can significantly increase image size. Consider if pydub's bundled capabilities are enough.
# For this iteration, focusing on portaudio for PyAudio.

# Copy only requirements first to leverage Docker cache
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Final Application Stage
FROM python:3.11-slim AS final

# Set working directory in the final image
WORKDIR /app

# Create a non-root user and group for security
RUN groupadd --system appgroup && useradd --system --gid appgroup appuser

# Install runtime dependencies (e.g., portaudio runtime, ffmpeg runtime if needed)
# This ensures that even if build tools are not in the final image, the shared libraries are.
RUN apt-get update && \
    apt-get install -y --no-install-recommends libportaudio2 ffmpeg curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*
# Note: Added ffmpeg here as well, as pydub might need it at runtime for various operations.
# Added curl and ca-certificates for healthcheck and general HTTPS calls.

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy the application source code
# If main.py is in src/, and other modules are in src/, copy src and other needed files
COPY ./src ./src
COPY ./prompts ./prompts
# Copy alembic.ini and migrations if migrations are to be run from/within the container
# For this setup, we assume migrations are run as a separate step or outside the app container usually.
# If running migrations on app startup is desired, these need to be uncommented.
# COPY ./alembic.ini .
# COPY ./migrations ./migrations

# Copy .env.template (the actual .env will be mounted or vars passed in compose)
# This is useful for reference or if some default non-sensitive fallbacks are read from it.
COPY ./.env.template .

# Ensure all files are owned by the appuser
# This should be one of the last steps before switching user.
RUN chown -R appuser:appgroup /app /opt/venv

# Switch to the non-root user
USER appuser

# Activate the virtual environment for the CMD instruction
# This ensures that the Python interpreter and packages from the venv are used.
ENV PATH="/opt/venv/bin:$PATH"
# Add /app to PYTHONPATH so `src.main` can be found if WORKDIR is /app.
# Also, ensure that modules within src (like logging_config) can be found using
# relative imports from other modules in src (e.g. `from .logging_config`).
ENV PYTHONPATH="/app:${PYTHONPATH}"

# Expose the port the app runs on
EXPOSE 8000

# Healthcheck (can be added here or in docker-compose.yml)
# python:slim does not have curl by default. A Python script or other tool would be needed.
# For now, this will be primarily in docker-compose.yml as per user spec.
# HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
#   CMD python -m http.client http://localhost:8000/healthz || exit 1
# (This requires http.client to be usable, which it is. Or use a small script.)

# Command to run the application
# Uvicorn needs to find src.main:app. If WORKDIR is /app, and src is copied into /app,
# then src.main:app should be correct. PYTHONPATH="/app" helps.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
