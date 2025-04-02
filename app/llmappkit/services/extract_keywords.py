from llmappkit.services.base_service import BaseService
from llmappkit.api.llm_client import LLMClient
from llmappkit.utils.prompt_loader import load_prompt
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_text_splitters import RecursiveCharacterTextSplitter

class ExtractKeyWords(BaseService):
    def __init__(self):
        self.llm_client = LLMClient()

    def get_prompts(self):
        system_prompt = load_prompt('system_prompts/extract_keywords_sys_prompt')
        user_prompt = load_prompt('user_prompts/extract_keywords_prompt')
        return system_prompt, user_prompt

    def process(self, text: str, use_threading=False) -> str:
        print(f"ExtractKeywords text:\n{text}\n\n")
        system_prompt, user_prompt = self.get_prompts()

        user_message = user_prompt.format(text=text)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        response = self.llm_client.generate_completion(messages, stream=False)

        return response.choices[0].message.content