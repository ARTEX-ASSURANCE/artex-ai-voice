import google.generativeai as genai
import os
import asyncio
from typing import Optional, Union, AsyncGenerator, List
from google.generativeai.types import GenerationConfig, ContentDict, PartDict, HarmCategory, HarmBlockThreshold, Tool
import sys # For standalone test logging

# Import logging configuration
from .logging_config import get_logger # Assuming it's in the same directory (src)
log = get_logger(__name__)

# Attempt to import ARGO_AGENT_TOOLS
try:
    from .gemini_tools import ARGO_AGENT_TOOLS
    log.debug("ARGO_AGENT_TOOLS imported successfully from .gemini_tools")
except ImportError:
    log.warn("ARGO_AGENT_TOOLS could not be imported. Function calling might not work as expected.")
    ARGO_AGENT_TOOLS = None

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
            log.error("Failed to configure Gemini API during client initialization.", error=str(e), exc_info=True)
            raise # Re-raise the exception as client cannot function

    def _prepare_model(self, tools_list: Optional[List[Tool]] = None) -> genai.GenerativeModel:
        final_tools = tools_list if tools_list is not None else ARGO_AGENT_TOOLS
        # log.debug(f"Preparing Gemini model with tools: {final_tools}") # Can be verbose
        return genai.GenerativeModel(
            self.model_name,
            safety_settings=DEFAULT_SAFETY_SETTINGS,
            tools=final_tools
        )

    async def generate_text_response(
        self,
        prompt_parts: List[Union[str, PartDict, ContentDict]],
        generation_config: Optional[GenerationConfig] = None,
        system_instruction: Optional[str] = None,
        tools_list: Optional[List[Tool]] = None
    ) -> genai.types.GenerateContentResponse:

        model = self._prepare_model(tools_list=tools_list)
        contents_to_send = []
        if system_instruction:
            contents_to_send.append({'role': 'system', 'parts': [{'text': system_instruction}]})

        if isinstance(prompt_parts, list) and all(isinstance(p, dict) for p in prompt_parts):
            contents_to_send.extend(prompt_parts)
        elif isinstance(prompt_parts, list):
            user_parts = [{'text': str(p)} if not isinstance(p, dict) else p for p in prompt_parts]
            contents_to_send.append({'role': 'user', 'parts': user_parts})
        elif isinstance(prompt_parts, str):
            contents_to_send.append({'role': 'user', 'parts': [{'text': prompt_parts}]})
        else:
            log.error("Unsupported type for prompt_parts.", type=type(prompt_parts).__name__)
            raise TypeError(f"Unsupported type for prompt_parts: {type(prompt_parts)}. Must be str or List.")

        current_retry = 0
        backoff_time = INITIAL_BACKOFF_SECONDS
        while current_retry < MAX_RETRIES:
            try:
                # log.debug("Generating content with Gemini.", contents=contents_to_send, config=generation_config)
                response = await model.generate_content_async(
                    contents=contents_to_send,
                    generation_config=generation_config,
                )
                return response
            except Exception as e:
                log.warn(f"Gemini API error. Retrying...", error=str(e), attempt=current_retry + 1, backoff_seconds=backoff_time, exc_info=True)
                await asyncio.sleep(backoff_time)
                current_retry += 1
                backoff_time = min(MAX_BACKOFF_SECONDS, backoff_time * 2)
        log.error(f"Failed to get response from Gemini after max retries.", retries=MAX_RETRIES)
        raise Exception(f"Failed to get response from Gemini after {MAX_RETRIES} retries.")

    async def stream_text_response(
        self,
        prompt_parts: List[Union[str, PartDict, ContentDict]],
        generation_config: Optional[GenerationConfig] = None,
        system_instruction: Optional[str] = None,
        tools_list: Optional[List[Tool]] = None
    ) -> AsyncGenerator[genai.types.GenerateContentResponse, None]:

        model = self._prepare_model(tools_list=tools_list)
        contents_to_send = []
        if system_instruction:
            contents_to_send.append({'role': 'system', 'parts': [{'text': system_instruction}]})

        if isinstance(prompt_parts, list) and all(isinstance(p, dict) for p in prompt_parts):
            contents_to_send.extend(prompt_parts)
        elif isinstance(prompt_parts, list):
            user_parts = [{'text': str(p)} if not isinstance(p, dict) else p for p in prompt_parts]
            contents_to_send.append({'role': 'user', 'parts': user_parts})
        elif isinstance(prompt_parts, str):
            contents_to_send.append({'role': 'user', 'parts': [{'text': prompt_parts}]})
        else:
            log.error("Unsupported type for prompt_parts in stream.", type=type(prompt_parts).__name__)
            raise TypeError(f"Unsupported type for prompt_parts: {type(prompt_parts)}. Must be str or List.")

        current_retry = 0
        backoff_time = INITIAL_BACKOFF_SECONDS
        while current_retry < MAX_RETRIES:
            try:
                # log.debug("Streaming content with Gemini.", contents=contents_to_send, config=generation_config)
                async for chunk in await model.generate_content_async(
                    contents=contents_to_send,
                    generation_config=generation_config,
                    stream=True
                ):
                    yield chunk
                return # End of stream
            except Exception as e:
                log.warn(f"Gemini API stream error. Retrying...", error=str(e), attempt=current_retry + 1, backoff_seconds=backoff_time, exc_info=True)
                await asyncio.sleep(backoff_time)
                current_retry += 1
                backoff_time = min(MAX_BACKOFF_SECONDS, backoff_time * 2)
        log.error(f"Failed to connect to Gemini stream after max retries.", retries=MAX_RETRIES)
        raise Exception(f"Failed to connect to Gemini stream after {MAX_RETRIES} retries.")

async def main_test_gemini_client():
    from dotenv import load_dotenv
    # Minimal logging for standalone test if not already configured by main app
    if not logging.getLogger().handlers:
        import structlog
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
        log.info("Response received.", text_snippet=full_response_1.text[:50] + "...")
        if not full_response_1.candidates or not full_response_1.candidates[0].content.parts:
            log.warn("No content parts in response for test 1.")
        elif full_response_1.candidates[0].finish_reason.name != "STOP":
             log.warn(f"Finish Reason for test 1: {full_response_1.candidates[0].finish_reason.name}")

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
                    log.info("Function call triggered in test.", tool_name=fc.name, tool_args=dict(fc.args))
                    called_tool = True
                    break
        if not called_tool:
            log.info("No function call in tool test response.", response_text=(response_with_tools.text[:100] + "..." if response_with_tools.text else "N/A"))

    except ValueError as ve: # Specifically for API key issues from constructor
        log.critical("Configuration Error in GeminiClient test.", error=str(ve), exc_info=True)
    except Exception as e:
        log.critical("Error in GeminiClient test.", error=str(e), exc_info=True)

if __name__ == "__main__":
    import logging # For standalone test logging setup
    asyncio.run(main_test_gemini_client())
