from llmappkit.api.llm_client import LLMClient as ExternalLLMClient

class LLMService:
    """Service layer to interface with the LLMAppKit's LLMClient."""
    
    def __init__(self, config):
        self.client = ExternalLLMClient(config)
        
    def generate_completion(self, messages, temperature=0.5, max_tokens=4096, stream=False, llm_model=None):
        """Proxy method to the underlying LLMClient."""
        return self.client.generate_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            llm_model=llm_model
        )
    
    def generate_embeddings(self, text, embedding_model=None):
        """Proxy method to the underlying LLMClient."""
        return self.client.generate_embeddings(
            text=text,
            embedding_model=embedding_model
        )