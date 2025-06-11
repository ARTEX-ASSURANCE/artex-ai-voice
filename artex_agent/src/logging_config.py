import logging
import structlog
import os
import sys
from typing import Optional, Any # Added Any for get_logger return type hint

# Store the original stdout for specific print-to-console needs if necessary
# _original_stdout = sys.stdout

def setup_logging(force_json: bool = False):
    """
    Configures structlog and standard library logging.
    Outputs JSON logs to stdout if LOG_FORMAT=json (env var) or force_json is True.
    Otherwise, uses a development-friendly console renderer.
    """
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    log_format_str = os.getenv("LOG_FORMAT", "console").lower() # Default to console

    # Determine if JSON output is forced by env var or parameter
    use_json_format = (log_format_str == "json") or force_json

    # Common processors for structlog
    shared_processors = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),      # Render stack info for exceptions
        structlog.dev.set_exc_info,                # Add exc_info to log record
        structlog.processors.format_exc_info,          # Format exception info nicely
        structlog.processors.TimeStamper(fmt="iso", utc=True), # ISO format, UTC timezone
        # structlog.processors.CallsiteParameterAdder( # Adds module, lineno, func_name
        #     [
        #         structlog.processors.CallsiteParameter.MODULE,
        #         structlog.processors.CallsiteParameter.LINENO,
        #         structlog.processors.CallsiteParameter.FUNC_NAME,
        #     ]
        # ),
        # Add custom processors for redaction here if needed in the future
    ]

    if use_json_format:
        # JSON output processors
        final_processors = shared_processors + [
            structlog.processors.dict_tracebacks, # Render tracebacks as dicts for JSON
            structlog.processors.JSONRenderer(),    # Render the log entry as a JSON string
        ]
        formatter_class = structlog.stdlib.ProcessorFormatter # For stdlib handler
        formatter_foreign_pre_chain = shared_processors + [structlog.processors.JSONRenderer()]
    else:
        # Console output processors (development-friendly)
        final_processors = shared_processors + [
            structlog.dev.ConsoleRenderer(  # Colorful, aligned output
                colors=True,
                exception_formatter=structlog.dev.plain_traceback # Simple traceback for console
            ),
        ]
        formatter_class = structlog.stdlib.ProcessorFormatter # For stdlib handler
        # For console, foreign_pre_chain can be simpler or just pass through
        formatter_foreign_pre_chain = shared_processors + [structlog.dev.ConsoleRenderer(colors=False)] # Basic console for foreign

    structlog.configure(
        processors=final_processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger, # Standard library logger compatibility
        cache_logger_on_first_use=True,
    )

    # Configure the underlying stdlib logging
    # This ProcessorFormatter bridges structlog output to stdlib handlers
    formatter = formatter_class.wrap_for_formatter(
        logger=logging.getLogger(), # Not strictly needed for this arg, but good practice
        # These processors are applied to messages from non-structlog loggers
        # (e.g., libraries using standard logging) before they are formatted by the handler.
        # For JSON, we want them to also become JSON. For console, pretty print.
        foreign_pre_chain=formatter_foreign_pre_chain,
    )

    handler = logging.StreamHandler(sys.stdout) # All logs to stdout

    # For JSON, the handler should not re-format if JSONRenderer was the last structlog step.
    # If JSONRenderer is the final structlog processor (as in `final_processors` for `use_json_format`),
    # the record passed to the handler is already a JSON string.
    # If ConsoleRenderer is used, it also produces a string.
    # So, no specific formatter is needed on the handler itself, or a pass-through.
    # However, `ProcessorFormatter.wrap_for_formatter` expects to be the formatter for the handler.
    handler.setFormatter(formatter) # This formatter handles both structlog and stdlib messages correctly

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Suppress overly verbose logs from some third-party libraries
    # These will still be processed by the root handler and its formatter (e.g., into JSON)
    # if their level is >= root_logger's level.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("speech_recognition").setLevel(logging.INFO)
    logging.getLogger("pydub").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.WARNING) # Can be noisy with debug logs
    logging.getLogger("grpc").setLevel(logging.WARNING) # gRPC can be very verbose

    # Test log to confirm setup
    # Use structlog's get_logger for application logs.
    # The initial "Logging setup complete" message is printed to stderr to avoid being formatted as JSON
    # if stdout is configured for JSON logs, making it more human-readable during startup.
    # Subsequent logs will follow the configured format (JSON or console).
    structlog.get_logger("logging_config_setup").info(
        "Initial logging setup complete.",
        log_level=log_level_str,
        log_format=("json" if use_json_format else "console")
    )


def get_logger(name: Optional[str] = None, **kwargs) -> Any: # structlog.stdlib.BoundLogger
    """
    Convenience function to get a structlog logger, optionally binding initial key-value pairs.
    """
    if name is None:
        # Try to automatically determine the name of the calling module
        # This is a bit of a hack and might not always be what you want.
        # Consider passing __name__ explicitly.
        try:
            frame = sys._getframe(1) # Get caller's frame
            name = frame.f_globals.get('__name__', 'unknown_module')
        except (AttributeError, ValueError, IndexError):
            name = 'app' # Default if automatic name detection fails
    return structlog.get_logger(name, **kwargs)

# Example usage (can be run directly for testing logging config):
if __name__ == "__main__":
    # os.environ["LOG_LEVEL"] = "DEBUG" # Test with DEBUG
    # os.environ["LOG_FORMAT"] = "json" # Test with JSON
    setup_logging()

    log = get_logger(__name__, component="TestComponent") # Pass __name__ or a specific context

    log.debug("This is a debug message.", data={"key": "value"})
    log.info("This is an info message.", user_id=123, action="test_log")
    log.warning("This is a warning message.")
    log.error("This is an error message.", error_code=500)
    try:
        x = 1 / 0
    except ZeroDivisionError:
        log.exception("An exception occurred (captured by log.exception).") # exc_info=True is implicit

    std_logger = logging.getLogger("stdlib_test_logger")
    std_logger.info("This is an info message from stdlib logger.")
    std_logger.error("This is an error message from stdlib logger with an arg: %s", "some_arg")

    log.info("Test logs from logging_config.py __main__ finished.")
