# artex_agent/src/logging_config.py
import logging
import structlog
import os
import sys # To print initial log setup message to stderr
from typing import Optional, Any # For type hints

# Store the original stdout to redirect specific messages if needed,
# though for JSON logging, all app logs should ideally go through structlog to stdout.
# For this setup, we'll just print the setup confirmation to stderr.
# _original_stdout = sys.stdout

# Define sensitive keys (case-insensitive for matching in the processor)
SENSITIVE_KEYS = {
    "nom", "prenom", "name", # Covers variations
    "email", "e_mail", "mail",
    "telephone", "phone", "phonenumber",
    "adresse", "address",
    "numero_securite_sociale", "num_secu", "social_security_number", "ssn",
    "numero_contrat", "police_number", "contract_number", "policynumber",
    "claim_id_ref", # If this is sensitive
    # "description_sinistre", # Handled by specific redaction_value check
    # Keys that might hold user's full input or detailed Gemini responses
    "user_input", "user_query", "gemini_response_text", "full_prompt", "prompt", "text_to_speak", # Handled by specific redaction
    # Keys within nested dicts, e.g. from function call args or results
    "tool_args", "function_response_content", "event_payload", "payload", "user_data", "data", # "data" is generic
    # Parameters from function calls (some might be sensitive by value, not just key name)
    # "type_sinistre", # Usually not sensitive itself
    "description_sinistre", # Explicitly handled for full text redaction
    # "date_survenance", # Less sensitive but often logged with PII
    "policy_id", # Alias for numero_contrat
}

# Fields that should have their string values fully redacted if they appear as keys
TEXT_REDACTION_KEYS = {
    "description_sinistre", "user_input", "user_query", "gemini_response_text",
    "full_prompt", "prompt", "text_to_speak", "details", "message", # Common keys for free text
}


def redact_sensitive_data_processor(_, __, event_dict: dict) -> dict:
    # Recursive redaction for nested dicts/lists
    def redact_recursive(item: Any) -> Any:
        if isinstance(item, dict):
            new_dict = {}
            for key, value in item.items():
                lower_key = key.lower()
                if lower_key in SENSITIVE_KEYS:
                    new_dict[key] = "[REDACTED]"
                elif lower_key in TEXT_REDACTION_KEYS and isinstance(value, str):
                    new_dict[key] = "[REDACTED_TEXT]"
                else:
                    new_dict[key] = redact_recursive(value) # Recurse for nested dicts/lists
            return new_dict
        elif isinstance(item, list):
            return [redact_recursive(elem) for elem in item]
        # Basic regex redaction for values (example, can be expanded if needed)
        # Currently, only key-based and specific text field redaction is implemented.
        # if isinstance(item, str):
        #     if re.match(r"[^@]+@[^@]+\.[^@]+", item): return "[REDACTED_EMAIL]"
        #     # Add more regex for phone numbers, SSNs in free text if needed
        return item

    # Process a copy to avoid modifying the original event_dict in unexpected ways by other processors
    return redact_recursive(event_dict.copy())


def setup_logging(log_level_str: Optional[str] = None) -> None:
    if log_level_str is None:
        log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()

    log_level = getattr(logging, log_level_str, logging.INFO)

    # Common processors for structlog
    shared_processors = [
        structlog.stdlib.filter_by_level, # Filter by level set on stdlib logger
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_sensitive_data_processor, # ADD THE REDACTION PROCESSOR HERE
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter, # Bridge to stdlib
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure the underlying stdlib logging to output JSON
    # This formatter will be used by structlog.stdlib.ProcessorFormatter
    # after structlog's own processors have run.
    stdlib_formatter = structlog.stdlib.ProcessorFormatter(
        # The foreign_pre_chain is processors that structlog runs on messages
        # from standard library loggers.
        foreign_pre_chain=shared_processors,
        # This processor is applied to the log record fields after structlog's processing
        # and before the standard library handler formats it. For JSON, this is key.
        processor=structlog.processors.JSONRenderer(),
    )

    handler = logging.StreamHandler(sys.stdout) # Output logs to stdout
    handler.setFormatter(stdlib_formatter)

    root_logger = logging.getLogger()
    # Remove any existing handlers to avoid duplicate logs if setup_logging is called multiple times
    # or if other libraries (like FastAPI/Uvicorn) add their own handlers.
    if root_logger.hasHandlers():
        for h in root_logger.handlers[:]: # Iterate over a copy of the list
            root_logger.removeHandler(h)

    root_logger.addHandler(handler)
    root_logger.setLevel(log_level) # Set the level on the root logger

    # Suppress overly verbose logs from some libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("speech_recognition").setLevel(logging.INFO) # Can be noisy on DEBUG
    logging.getLogger("pyaudio").setLevel(logging.WARNING)
    logging.getLogger("google.auth.transport.requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.INFO)
    logging.getLogger("asyncio").setLevel(logging.WARNING) # Can be very noisy on DEBUG

    # Use a structlog logger to announce completion, ensuring it also goes through the setup
    initial_log = structlog.get_logger("artex_agent.logging_config")
    initial_log.info("Logging setup complete.", log_level=log_level_str, output="json_stdout")
    # print(f"Logging setup complete. Log level: {log_level_str}. Output: JSON to stdout.", file=sys.stderr)

def get_logger(name: Optional[str] = None) -> Any: # Actually structlog.stdlib.BoundLogger
    # Ensure setup_logging has been called once
    if not structlog.is_configured(): # Basic check, real apps might use a flag
         print("CRITICAL WARNING: Structlog not configured via setup_logging() before get_logger() called. Logging will likely fail or be misconfigured. Call setup_logging() at app start.", file=sys.stderr)
         # Attempt a basic configuration if not done, though this is not ideal and might not work as expected.
         # setup_logging() # Avoid calling here, should be explicit in app entry points. This can lead to recursive issues or misconfiguration.

    # This will get a logger wrapped by structlog that uses the stdlib backend
    return structlog.get_logger(name if name else "app")


# For direct testing of this module:
if __name__ == "__main__":
    # Example of how setup_logging might be called with a specific level for testing
    # os.environ["LOG_LEVEL"] = "DEBUG" # Override for this test run
    setup_logging(log_level_str="DEBUG") # Call directly for testing this script

    log = get_logger("my_test_logger")
    log.debug("This is a debug message from logging_config_test.", data={"test": True, "email": "debug@example.com"})
    log.info("This is an info message from logging_config_test.", user_id=123, nom="Doe", prenom="John")
    log.warning("This is a warning message.", telephone="0123456789")

    sensitive_payload = {
        "user_details": {
            "name": "Jane Secret",
            "contact": {
                "email": "jane.secret@example.com",
                "numero_contrat": "CONTRAT_XYZ_789"
            }
        },
        "description_sinistre": "User reported car was hit by a tree on Main St. Policy POL98765."
    }
    log.info("Sensitive payload test", payload=sensitive_payload)
    log.info("Another sensitive test", text_to_speak="My SSN is 123-456-7890 and my policy is NC54321.")


    try:
        raise ValueError("A test value error for logging.")
    except ValueError:
        log.error("An error occurred", exc_info=True, details={"numero_contrat": "NC12345", "reason": "timeout"})

    # Test logging from a standard library logger to see if it's captured by structlog
    stdlib_logger = logging.getLogger("my_stdlib_test_logger")
    stdlib_logger.info("Info message from stdlib_logger, with email: stdlib_user@example.com.")
    stdlib_logger.error("Error message from stdlib_logger, with contract_number: STD_ERR_POL_001.")

    # Test another call to get_logger
    log2 = get_logger() # Default name 'app'
    log2.info("Another message from default 'app' logger.", user_query="What is my SSN?")

    print("\nNOTE: If testing this script directly, ensure LOG_LEVEL env var is not set, or set to DEBUG to see all messages.", file=sys.stderr)
    print("Output above should be JSON lines, with sensitive data redacted.", file=sys.stderr)
