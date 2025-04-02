from llmappkit.api.llm_client import LLMClient
from llmappkit.utils.prompt_loader import load_prompt
import json

class ApplicantScorer:
    def __init__(self):
        self.llm_client = LLMClient()

    def score_applicant(self, job_description, applicant, temperature=0.3, max_tokens=4096, stream=False):
        system_prompt = load_prompt('system_prompts/applicant_scorer_sys_prompt')
        user_prompt = load_prompt('user_prompts/applicant_scorer_prompt')

        user_message = user_prompt.format(
            job_description=job_description,
            applicant=applicant
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        return self.llm_client.generate_completion(messages, temperature=temperature, max_tokens=4096, stream=stream)
        
