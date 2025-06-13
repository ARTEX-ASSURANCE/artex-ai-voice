import google.generativeai as genai
import os
import asyncio
from typing import Optional, Union, AsyncGenerator, List, Dict # Added Dict for helper return type
from google.generativeai.types import GenerationConfig, ContentDict, PartDict, HarmCategory, HarmBlockThreshold, Tool
import sys # For standalone test logging

# Import logging configuration
from .logging_config import get_logger # Assuming it's in the same directory (src)
log = get_logger(__name__)

# Attempt to import ARTEX_AGENT_TOOLS
try:
    from .gemini_tools import ARTEX_AGENT_TOOLS
    log.debug("ARTEX_AGENT_TOOLS imported successfully from .gemini_tools")
except ImportError:
    log.warn("ARTEX_AGENT_TOOLS could not be imported. Function calling might not work as expected.")
    ARTEX_AGENT_TOOLS = None

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 16

DEFAULT_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-1.5-flash-latest"):
        effective_api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")
        if not effective_api_key:
            log.error("GEMINI_API_KEY not provided or found in environment.")
            raise ValueError("GEMINI_API_KEY not provided or found in environment.")

        try:
            genai.configure(api_key=effective_api_key)
            self.model_name = model_name
            log.info(f"GeminiClient initialized successfully with model: {self.model_name}")
        except Exception as e:
            log.error("Failed to configure Gemini API during client initialization.", error_str=str(e), exc_info=True) # Use error_str
            raise # Re-raise the exception as client cannot function

    def _prepare_model(self, tools_list: Optional[List[Tool]] = None) -> genai.GenerativeModel:
        final_tools = tools_list if tools_list is not None else ARTEX_AGENT_TOOLS
        # log.debug(f"Preparing Gemini model with tools: {final_tools}") # Can be verbose
        return genai.GenerativeModel(
            self.model_name,
            safety_settings=DEFAULT_SAFETY_SETTINGS,
            tools=final_tools
        )

    async def generate_text_response(
        self,
        prompt_parts: List[Union[str, PartDict, ContentDict]], # Changed name for clarity
        generation_config: Optional[GenerationConfig] = None,
        system_instruction: Optional[str] = None,
        tools_list: Optional[List[Tool]] = None
    ) -> genai.types.GenerateContentResponse: # Returns the full response object

        model = self._prepare_model(tools_list=tools_list)
        contents_to_send = []
        if system_instruction:
            # For models like gemini-1.5-flash, system instruction is part of the 'contents' list
            contents_to_send.append({'role': 'system', 'parts': [{'text': system_instruction}]})

        # Handle different input types for prompt_parts
        if isinstance(prompt_parts, list) and all(isinstance(p, dict) and 'role' in p and 'parts' in p for p in prompt_parts):
            # This is already a valid 'contents' list (history)
            contents_to_send.extend(prompt_parts)
        elif isinstance(prompt_parts, list):
            # list of strings or PartDicts, assume it's for a single 'user' turn
            user_parts_processed = []
            for p_item in prompt_parts:
                if isinstance(p_item, str): user_parts_processed.append({'text': p_item})
                elif isinstance(p_item, dict): user_parts_processed.append(p_item) # Already a PartDict
                else: log.warn("Unsupported item in prompt_parts list, skipping.", item_type=type(p_item))
            if user_parts_processed:
                contents_to_send.append({'role': 'user', 'parts': user_parts_processed})
        elif isinstance(prompt_parts, str):
            # Single string prompt
            contents_to_send.append({'role': 'user', 'parts': [{'text': prompt_parts}]})
        else:
            log.error("Unsupported type for prompt_parts argument.", type=type(prompt_parts).__name__)
            raise TypeError(f"Unsupported type for prompt_parts: {type(prompt_parts)}. Must be str or List of ContentDict/PartDict/str.")

        current_retry = 0
        backoff_time = INITIAL_BACKOFF_SECONDS
        while current_retry < MAX_RETRIES:
            try:
                # log.debug("Generating content with Gemini.", contents_for_api=contents_to_send, config=generation_config)
                response = await model.generate_content_async(
                    contents=contents_to_send, # Pass the prepared list
                    generation_config=generation_config,
                )
                return response # Return the full response object
            except Exception as e:
                log.warn(f"Gemini API error. Retrying...", error_str=str(e), attempt=current_retry + 1, backoff_seconds=backoff_time, exc_info=True) # Use error_str
                await asyncio.sleep(backoff_time)
                current_retry += 1
                backoff_time = min(MAX_BACKOFF_SECONDS, backoff_time * 2)
        log.error(f"Failed to get response from Gemini after max retries.", retries=MAX_RETRIES)
        raise Exception(f"Failed to get response from Gemini after {MAX_RETRIES} retries.")

    async def stream_text_response(
        self,
        prompt_parts: List[Union[str, PartDict, ContentDict]], # Changed name for clarity
        generation_config: Optional[GenerationConfig] = None,
        system_instruction: Optional[str] = None,
        tools_list: Optional[List[Tool]] = None
    ) -> AsyncGenerator[genai.types.GenerateContentResponse, None]:

        model = self._prepare_model(tools_list=tools_list)
        contents_to_send = [] # Same logic as generate_text_response
        if system_instruction:
            contents_to_send.append({'role': 'system', 'parts': [{'text': system_instruction}]})

        if isinstance(prompt_parts, list) and all(isinstance(p, dict) and 'role' in p and 'parts' in p for p in prompt_parts):
            contents_to_send.extend(prompt_parts)
        elif isinstance(prompt_parts, list):
            user_parts_processed = []
            for p_item in prompt_parts:
                if isinstance(p_item, str): user_parts_processed.append({'text': p_item})
                elif isinstance(p_item, dict): user_parts_processed.append(p_item)
                else: log.warn("Unsupported item in prompt_parts list for stream, skipping.", item_type=type(p_item))
            if user_parts_processed:
                contents_to_send.append({'role': 'user', 'parts': user_parts_processed})
        elif isinstance(prompt_parts, str):
            contents_to_send.append({'role': 'user', 'parts': [{'text': prompt_parts}]})
        else:
            log.error("Unsupported type for prompt_parts argument in stream.", type=type(prompt_parts).__name__)
            raise TypeError(f"Unsupported type for prompt_parts: {type(prompt_parts)}. Must be str or List of ContentDict/PartDict/str.")

        current_retry = 0
        backoff_time = INITIAL_BACKOFF_SECONDS
        while current_retry < MAX_RETRIES:
            try:
                # log.debug("Streaming content with Gemini.", contents_for_api=contents_to_send, config=generation_config)
                async for chunk in await model.generate_content_async(
                    contents=contents_to_send, # Pass the prepared list
                    generation_config=generation_config,
                    stream=True
                ):
                    yield chunk
                return # End of stream
            except Exception as e:
                log.warn(f"Gemini API stream error. Retrying...", error_str=str(e), attempt=current_retry + 1, backoff_seconds=backoff_time, exc_info=True) # Use error_str
                await asyncio.sleep(backoff_time)
                current_retry += 1
                backoff_time = min(MAX_BACKOFF_SECONDS, backoff_time * 2)
        log.error(f"Failed to connect to Gemini stream after max retries.", retries=MAX_RETRIES)
        raise Exception(f"Failed to connect to Gemini stream after {MAX_RETRIES} retries.")

# Helper function to extract usage metadata
def extract_usage_metadata(response: genai.types.GenerateContentResponse) -> Dict[str, int]:
    """Extracts token usage data from Gemini response into a dictionary."""
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if hasattr(response, 'usage_metadata') and response.usage_metadata:
        usage["prompt_tokens"] = response.usage_metadata.prompt_token_count
        # Gemini API often gives total_token_count and prompt_token_count.
        # Completion tokens might be in candidates_token_count or derived.
        usage["completion_tokens"] = response.usage_metadata.candidates_token_count # Often completion for single candidate
        usage["total_tokens"] = response.usage_metadata.total_token_count

        # Fallback if candidates_token_count is not directly completion tokens or if total seems more reliable
        if usage["completion_tokens"] == 0 and usage["total_tokens"] > usage["prompt_tokens"]:
            usage["completion_tokens"] = usage["total_tokens"] - usage["prompt_tokens"]
            # log.debug("Derived completion_tokens from total and prompt.", derived_completion=usage["completion_tokens"])

        # Ensure total_tokens is consistent if it was initially 0 or if derived completion is used
        if usage["total_tokens"] == 0 and (usage["prompt_tokens"] > 0 or usage["completion_tokens"] > 0):
            usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
            # log.debug("Calculated total_tokens from prompt and completion.", calc_total=usage["total_tokens"])
        # Optional: Warn about inconsistencies if all three are present but don't add up.
        # For now, we prioritize values directly from API if present.
    else:
        log.warn("No usage_metadata found in the Gemini response.")

    return usage

async def main_test_gemini_client():
    from dotenv import load_dotenv
    # Minimal logging for standalone test if not already configured by main app
    if not logging.getLogger().handlers: # Check if root logger has handlers (basic check)
        import structlog # Keep structlog import here for this specific case
        structlog.configure(processors=[structlog.dev.ConsoleRenderer()])
        logging.basicConfig(level="INFO", stream=sys.stdout)
        log.info("Minimal logging configured for gemini_client.py standalone test.")

    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if not os.path.exists(dotenv_path):
        log.warn(f".env file not found at {dotenv_path}. Relying on existing env vars for test.")
        load_dotenv()
    else:
        load_dotenv(dotenv_path=dotenv_path)
        log.info(f".env file loaded from {dotenv_path} for test.")

    if not os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") == "YOUR_GEMINI_API_KEY_HERE":
        log.critical("GEMINI_API_KEY not found or is placeholder. Cannot run GeminiClient test.")
        return

    try:
        client = GeminiClient()

        log.info("--- Testing non-streaming (simple prompt) ---")
        test_contents_1 = [{'role': 'user', 'parts': [{'text': "Tell me a fun fact about Python programming language."}]}]
        full_response_1 = await client.generate_text_response(
            prompt_parts=test_contents_1,
            system_instruction="Be very enthusiastic and use emojis."
        )
        log.info("Response received.", text_snippet=(full_response_1.text[:50] + "..." if full_response_1.text else "N/A"))

        # Extract and log usage for test 1
        usage_info_1 = extract_usage_metadata(full_response_1)
        log.info("Token Usage (Test 1)", **usage_info_1) # Log as structured data

        if not full_response_1.candidates or not full_response_1.candidates[0].content.parts:
            log.warn("No content parts in response for test 1.")
        elif full_response_1.candidates[0].finish_reason.name != "STOP":
             log.warn(f"Finish Reason for test 1: {full_response_1.candidates[0].finish_reason.name}")

        # Simple check for usage data presence for test purposes
        if usage_info_1["total_tokens"] == 0 and full_response_1.text: # If there's text, there should be tokens
            log.warn("Usage metadata reported zero tokens despite response having text.", response_text_present=bool(full_response_1.text))

        log.info("--- Testing streaming ---")
        test_contents_2 = [{'role': 'user', 'parts': [{'text': "Write a short haiku about a robot learning to dream."}]}]
        full_streamed_text = ""
        print("Streamed Haiku: ", end="") # Direct print for stream visualization
        async for chunk in client.stream_text_response(
            prompt_parts=test_contents_2,
            system_instruction="You are a famous poet."
        ):
            print(chunk.text, end="") # Direct print for stream visualization
            full_streamed_text += chunk.text
        print("\nStream finished.")
        log.info("Streaming test completed.", full_text_length=len(full_streamed_text))
        if not full_streamed_text.strip():
            log.warn("Streamed response was empty.")

        log.info("--- Testing function call with ARGO_AGENT_TOOLS ---")
        test_contents_3 = [
             {'role': 'user', 'parts': [{'text': "Je veux connaître mon dernier remboursement pour la police AUTO-789."}]}
        ]
        response_with_tools = await client.generate_text_response(
            prompt_parts=test_contents_3,
            system_instruction="Tu es un assistant et tu peux utiliser des outils. Utilise l'outil get_last_reimbursement si on te demande le dernier remboursement."
            # tools_list=ARGO_AGENT_TOOLS is used by default in _prepare_model if not None
        )

        called_tool = False
        if response_with_tools.candidates and response_with_tools.candidates[0].content and response_with_tools.candidates[0].content.parts:
            for part in response_with_tools.candidates[0].content.parts:
                if part.function_call:
                    fc = part.function_call
                    log.info("Function call triggered in test.", tool_name=fc.name, tool_args=str(dict(fc.args))) # Log args as str
                    called_tool = True
                    break
        if not called_tool:
            log.info("No function call in tool test response.", response_text=(response_with_tools.text[:100] + "..." if response_with_tools.text else "N/A"))

        # Extract and log usage for test 3 (function call)
        usage_info_3 = extract_usage_metadata(response_with_tools)
        log.info("Token Usage (Test 3 - Function Call)", **usage_info_3)

    except ValueError as ve: # Specifically for API key issues from constructor
        log.critical("Configuration Error in GeminiClient test.", error_str=str(ve), exc_info=True) # Use error_str
    except Exception as e:
        log.critical("Error in GeminiClient test.", error_str=str(e), exc_info=True) # Use error_str

if __name__ == "__main__":
    import logging # For standalone test logging setup
    # Wrapped main_test_gemini_client in another async function for cleaner asyncio.run call
    async def run_tests_main():
        await main_test_gemini_client()
    asyncio.run(run_tests_main())
