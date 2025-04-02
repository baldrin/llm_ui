#from langchain_community.vectorstores import Chroma
from langchain_chroma import Chroma
from llmappkit.utils.embeddings import databricks_embeddings

class VectorStoreSingleton:
    _instances = {}

    @classmethod
    def get_instance(cls, collection_name="resume_documents", persist_directory="chroma_storage"):
        if collection_name not in cls._instances:
            cls._instances[collection_name] = Chroma(
                collection_name=collection_name,
                embedding_function=databricks_embeddings,
                persist_directory=persist_directory
            )
        return cls._instances[collection_name]

def document_exists_in_chroma_db(document_name: str, collection_name="resume_documents", persist_directory="chroma_storage") -> bool:
    try:
        vectorstore = VectorStoreSingleton.get_instance(collection_name, persist_directory)

        data = vectorstore.get(
            where={"source" : document_name},
            include=["metadatas"]
        )

        if data['metadatas'] and data['metadatas'][0]['source'] == document_name:
            print(f'It was found in the collection: {collection_name}')
            return True

    except Exception as e:
        print(f"Error checking document existence in Chroma DB: {e}")

    print(f'It was not found in the collection: {collection_name}')
    return False

def get_full_resume_from_db(document_name, collection_name="full_resume_and_short_summary", persist_directory="chroma_storage"):
    vectorstore = VectorStoreSingleton.get_instance(collection_name, persist_directory)

    results = vectorstore.get(
            where={"source" : document_name},
        )

    return(results['documents'][0])


def get_applicants_by_filters(filters=None, collection_name="full_resume_and_short_summary", persist_directory="chroma_storage"):
    vectorstore = VectorStoreSingleton.get_instance(collection_name, persist_directory)

    if not filters:
        results = vectorstore.get(
           include=["metadatas", "documents"] 
        )
    else:
        results = vectorstore.get(
            where=filters,
            include=["metadatas", "documents"] 
        )
        
    return(results)

def get_applicants_by_date_range(start_date, end_date, collection_name="full_resume_and_short_summary", persist_directory="chroma_storage"):
    vectorstore = VectorStoreSingleton.get_instance(collection_name, persist_directory)

    results = vectorstore.get(
        where={"date_applied": {"$gte": start_date, "$lte": end_date}},
        include=["metadatas"] 

    )

    return(results['documents'])

def get_short_summary_from_db(document_name, collection_name="full_resume_and_short_summary", persist_directory="chroma_storage"):
    vectorstore = VectorStoreSingleton.get_instance(collection_name, persist_directory)

    results = vectorstore.get(
            where={"source" : document_name},
        )

    return results['metadatas'][0]['short_summary']
