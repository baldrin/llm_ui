from typing import List, Dict
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

def split_contents(contents: str, file_name: str, chunk_size=1024, chunk_overlap=100, metadata: Dict = {}) -> List[Document]:

    try:
        print("Splitting contents...")
        combined_metadata = {"source": file_name}
        combined_metadata.update(metadata)

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        chunks = text_splitter.create_documents(texts=[contents], metadatas=[combined_metadata])

        for index, chunk in enumerate(chunks):
            chunk.metadata['chunk_index'] = index
            print(f'chunk index {index}')
        
        #for chunk in chunks:
            #print(f'REMOVE THIS Chunks: {chunk}\n\n')
    except Exception as e:
        raise RuntimeError(f"Error splitting PDF contents: {e}")
    return chunks
