from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_text_splitters import RecursiveCharacterTextSplitter
import math

class BaseService:
    def get_prompts(self, **kwargs):
        raise NotImplementedError

    def process(self, **kwargs):
        raise NotImplementedError

    def execute(self, text: str, chunk_size:int=1024, use_threading:bool=False, max_workers:int=1, **kwargs):
        if use_threading:
            return self._process_in_chunks(text, chunk_size, max_workers, **kwargs)
        else:
            return self.process(text=text, **kwargs)

    def _process_in_chunks(self, text, chunk_size, max_workers, **kwargs):
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=100,
        )

        chunks = text_splitter.create_documents([text])
        chunks = [chunk.page_content for chunk in chunks]
        results = [None] * len(chunks) # Preallocate 

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_chunk_index = {executor.submit(self.process, text=chunk, **kwargs): i for i, chunk in enumerate(chunks)}
            for future in as_completed(future_to_chunk_index):
                chunk_index = future_to_chunk_index[future]
                results[chunk_index] = future.result()

        return self._recombine_chunks(results)

    def _recombine_chunks(self, chunks):
        return ' '.join(chunks)

        



        

    

