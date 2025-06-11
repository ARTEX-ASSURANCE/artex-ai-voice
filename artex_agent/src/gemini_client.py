import google.generativeai as genai
import os
import asyncio
from typing import Optional, Union, AsyncGenerator, List
from google.generativeai.types import GenerationConfig, ContentDict, PartDict, HarmCategory, HarmBlockThreshold, Tool

# Attempt to import ARGO_AGENT_TOOLS, handle potential ImportError if gemini_tools.py doesn't exist or is empty
try:
    from .gemini_tools import ARGO_AGENT_TOOLS
except ImportError:
    print("Warning: ARGO_AGENT_TOOLS could not be imported from .gemini_tools. Function calling might not work as expected.")
    ARGO_AGENT_TOOLS = None # Define as None or empty list if import fails

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
            raise ValueError("GEMINI_API_KEY not provided or found in environment.")
        genai.configure(api_key=effective_api_key)
        self.model_name = model_name

    def _prepare_model(self, tools_list: Optional[List[Tool]] = None) -> genai.GenerativeModel:
        # If tools_list is explicitly passed, use it. Otherwise, use the imported ARGO_AGENT_TOOLS.
        final_tools = tools_list if tools_list is not None else ARGO_AGENT_TOOLS
        return genai.GenerativeModel(
            self.model_name,
            safety_settings=DEFAULT_SAFETY_SETTINGS,
            tools=final_tools
        )

    async def generate_text_response(
        self,
        prompt_parts: List[Union[str, PartDict, ContentDict]],
        generation_config: Optional[GenerationConfig] = None,
        system_instruction: Optional[str] = None, # Added system_instruction parameter
        tools_list: Optional[List[Tool]] = None # Allow overriding default tools
    ) -> genai.types.GenerateContentResponse:

        model = self._prepare_model(tools_list=tools_list) # tools_list here will use ARGO_AGENT_TOOLS if None

        contents_to_send = []
        if system_instruction:
            contents_to_send.append({'role': 'system', 'parts': [{'text': system_instruction}]})

        # Ensure prompt_parts are correctly formatted as ContentDict if they are not already
        if isinstance(prompt_parts, list) and all(isinstance(p, dict) for p in prompt_parts):
            contents_to_send.extend(prompt_parts) # Assumes prompt_parts is already List[ContentDict]
        elif isinstance(prompt_parts, list): # List of strings or PartDicts
            user_parts = []
            for p_item in prompt_parts:
                if isinstance(p_item, str):
                    user_parts.append({'text': p_item})
                elif isinstance(p_item, dict): # Assumed to be PartDict
                    user_parts.append(p_item)
                else:
                    # Handle other types if necessary, or raise error
                    user_parts.append({'text': str(p_item)})
            contents_to_send.append({'role': 'user', 'parts': user_parts})
        elif isinstance(prompt_parts, str): # Single string prompt
            contents_to_send.append({'role': 'user', 'parts': [{'text': prompt_parts}]})
        else:
            raise TypeError(f"Unsupported type for prompt_parts: {type(prompt_parts)}. Must be str or List.")


        current_retry = 0
        backoff_time = INITIAL_BACKOFF_SECONDS
        while current_retry < MAX_RETRIES:
            try:
                response = await model.generate_content_async(
                    contents=contents_to_send,
                    generation_config=generation_config,
                )
                return response
            except Exception as e:
                print(f"Gemini API error: {e}. Retrying in {backoff_time}s...")
                await asyncio.sleep(backoff_time)
                current_retry += 1
                backoff_time = min(MAX_BACKOFF_SECONDS, backoff_time * 2)
        raise Exception(f"Failed to get response from Gemini after {MAX_RETRIES} retries.")

    async def stream_text_response(
        self,
        prompt_parts: List[Union[str, PartDict, ContentDict]],
        generation_config: Optional[GenerationConfig] = None,
        system_instruction: Optional[str] = None, # Added system_instruction parameter
        tools_list: Optional[List[Tool]] = None # Allow overriding default tools
    ) -> AsyncGenerator[genai.types.GenerateContentResponse, None]:

        model = self._prepare_model(tools_list=tools_list) # tools_list here will use ARGO_AGENT_TOOLS if None

        contents_to_send = []
        if system_instruction:
            contents_to_send.append({'role': 'system', 'parts': [{'text': system_instruction}]})

        if isinstance(prompt_parts, list) and all(isinstance(p, dict) for p in prompt_parts):
            contents_to_send.extend(prompt_parts)
        elif isinstance(prompt_parts, list):
            user_parts = []
            for p_item in prompt_parts:
                if isinstance(p_item, str): user_parts.append({'text': p_item})
                elif isinstance(p_item, dict): user_parts.append(p_item)
                else: user_parts.append({'text': str(p_item)})
            contents_to_send.append({'role': 'user', 'parts': user_parts})
        elif isinstance(prompt_parts, str):
            contents_to_send.append({'role': 'user', 'parts': [{'text': prompt_parts}]})
        else:
            raise TypeError(f"Unsupported type for prompt_parts: {type(prompt_parts)}. Must be str or List.")

        current_retry = 0
        backoff_time = INITIAL_BACKOFF_SECONDS
        while current_retry < MAX_RETRIES:
            try:
                async for chunk in await model.generate_content_async(
                    contents=contents_to_send,
                    generation_config=generation_config,
                    stream=True
                ):
                    yield chunk
                return
            except Exception as e:
                print(f"Gemini API stream error: {e}. Retrying in {backoff_time}s...")
                await asyncio.sleep(backoff_time)
                current_retry += 1
                backoff_time = min(MAX_BACKOFF_SECONDS, backoff_time * 2)
        raise Exception(f"Failed to connect to Gemini stream after {MAX_RETRIES} retries.")

async def main_test_gemini_client():
    from dotenv import load_dotenv
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if not os.path.exists(dotenv_path):
        print(f"Warning: .env file not found at {dotenv_path}. Attempting to load from default location or rely on existing env vars.")
        load_dotenv()
    else:
        load_dotenv(dotenv_path=dotenv_path)
        print(f".env file loaded from {dotenv_path}")

    if not os.getenv("GEMINI_API_KEY"):
        print("CRITICAL: GEMINI_API_KEY not found after attempting to load .env. Cannot run test.")
        return

    try:
        client = GeminiClient()

        print("\n--- Testing non-streaming (simple prompt) ---")
        test_contents_1 = [{'role': 'user', 'parts': [{'text': "Tell me a fun fact about Python programming language."}]}]
        full_response_1 = await client.generate_text_response(
            prompt_parts=test_contents_1,
            system_instruction="Be very enthusiastic and use emojis."
        )
        print(f"Response text: {full_response_1.text}")
        if not full_response_1.candidates or not full_response_1.candidates[0].content.parts:
            print("Warning: No content parts in response for test 1.")
        elif full_response_1.candidates[0].finish_reason.name != "STOP":
             print(f"Finish Reason for test 1: {full_response_1.candidates[0].finish_reason.name}")

        print("\n--- Testing streaming ---")
        test_contents_2 = [{'role': 'user', 'parts': [{'text': "Write a short haiku about a robot learning to dream."}]}]
        full_streamed_text = ""
        async for chunk in client.stream_text_response(
            prompt_parts=test_contents_2,
            system_instruction="You are a famous poet."
        ):
            print(chunk.text, end="")
            full_streamed_text += chunk.text
        print("\nStream finished.")
        if not full_streamed_text.strip():
            print("Warning: Streamed response was empty.")

        print("\n--- Testing function call with ARGO_AGENT_TOOLS ---")
        test_contents_3 = [
             {'role': 'user', 'parts': [{'text': "Je veux connaître mon dernier remboursement pour la police AUTO-789."}]}
        ]
        # ARGO_AGENT_TOOLS will be used by default by _prepare_model if tools_list is None in generate_text_response
        response_with_tools = await client.generate_text_response(
            prompt_parts=test_contents_3,
            system_instruction="Tu es un assistant et tu peux utiliser des outils pour répondre aux questions. Utilise l'outil get_last_reimbursement si on te demande le dernier remboursement."
        )

        called_tool = False
        if response_with_tools.candidates and response_with_tools.candidates[0].content and response_with_tools.candidates[0].content.parts:
            for part in response_with_tools.candidates[0].content.parts:
                if part.function_call:
                    fc = part.function_call
                    print(f"Function call triggered: {fc.name} with args: {dict(fc.args)}")
                    called_tool = True
                    break

        if not called_tool:
            print(f"No function call in response. Text: {response_with_tools.text if response_with_tools.text else 'No text and no function call.'}")

    except ValueError as ve:
        print(f"Configuration Error in GeminiClient test: {ve}")
    except Exception as e:
        print(f"Error in GeminiClient test: {e}")

if __name__ == "__main__":
    asyncio.run(main_test_gemini_client())
