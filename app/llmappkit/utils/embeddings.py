from langchain.embeddings.base import Embeddings
from llmappkit.api.llm_client import LLMClient

class DatabricksEmbeddings(Embeddings):
    def __init__(self):
        super().__init__()
        self.client = LLMClient()        

    def get_databricks_embeddings(self, text):
        return self.client.generate_embeddings(text)

    def embed_documents(self, texts):
        return [self.get_databricks_embeddings(text) for text in texts]

    def embed_query(self, text):
        return self.get_databricks_embeddings(text)

    

databricks_embeddings = DatabricksEmbeddings()