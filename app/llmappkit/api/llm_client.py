import openai
from openai import ChatCompletion
#from llmappkit.utils.config_loader import load_config
import httpx
import ast

class LLMClient:
	def __init__(self, config):
		client = httpx.Client(verify=config['databricks_certs'])
		self.client = openai.OpenAI(api_key=config['llm_auth_token'], base_url=config['base_url'], http_client=client)
		self.llm_model = None # config['llm_model']
		self.embedding_model = config['embedding_model']

	def generate_completion(self, messages, temperature=0.5, max_tokens=4096, stream=False, llm_model=None):
		if llm_model is None:
			llm_model = self.llm_model
		
		return self.client.chat.completions.create(
			model=llm_model,
			messages=messages,
			temperature=temperature,
			max_tokens=max_tokens,
			stream=stream
		)

	def generate_embeddings(self, text, embedding_model=None):
		if embedding_model is None:
			embedding_model = self.embedding_model
		
		embeddings = self.client.embeddings.create(
        	input=text,
        	model=embedding_model,
    	)
		
		return embeddings.data[0].embedding

	def query_llm_with_function_call(self, original_query, function_handler, temperature=0.5, max_tokens=4096, stream=False, llm_model=None):
		if llm_model is None:
			llm_model = self.llm_model

		functions = [
			{
				"type": "function",
				"function": {
					"name": "search_for_candidates",
					"description": "Search for candidate resumes from a vector database",
					"parameters": {
						"type": "object",
						"properties": {
							"search_query": {
								"type": "string",
								"description": "A question or phrase containing the candidate search criteria"
							}
						},
						"required": [
							"search_query"
						]
					}
				}				
			},
			{
				"type": "function",
				"function": {
					"name": "get_full_resume",
					"description": "Get the full resume from the vectorstore by using the resume file name",
					"parameters": {
						"type": "object",
						"properties": {
							"file_name": {
								"type": "string",
								"description": "The file name of the resume for a given candidate"
							}
						},
						"required": [
							"file_name"
						]
					}
				}				
			},
			{
				"type": "function",
				"function": {
					"name": "get_short_candidate_summary",
					"description": "Provided a short summary of the candidate qualifications when requested",
					"parameters": {
						"type": "object",
						"properties": {
							"file_name": {
								"type": "string",
								"description": "The file name of the resume for a given candidate"
							}
						},
						"required": [
							"file_name"
						]
					}
				}				
			},
			{
				"type": "function",
				"function": {
					"name": "evaluate_resume_against_job_description",
					"description": "Provided a short summary of the candidate qualifications when requested",
					"parameters": {
						"type": "object",
						"properties": {
							"resume": {
								"type": "string",
								"description": "The resume to compare against the job description"
							}
						},
						"required": [
							"resume",
							"current_job_description"
						]
					}
				}				
			}
		]

		response = self.client.chat.completions.create(
			model=llm_model,
			messages=[
				{
					"role": "user", "content": original_query,
				}
			],
			tools=functions,
			temperature=temperature,
			max_tokens=max_tokens,
			stream=stream
		)

		message = response.choices[0].message
		print(f'\nFunction call: {message}]\n\n')
		if hasattr(message, 'tool_calls') and message.tool_calls is not None:
			tool_call = message.tool_calls[0]
			arguments = ast.literal_eval(tool_call.function.arguments)
			function_name = tool_call.function.name
			
			if function_name == "search_for_candidates":
				updated_search_query = arguments['search_query']
				return function_handler(original_query, updated_search_query, function_name)
			if function_name == "get_full_resume":
				updated_search_query = arguments['file_name']
				return function_handler(original_query, updated_search_query, function_name)
			if function_name == "get_short_candidate_summary":
				updated_search_query = arguments['file_name']
				return function_handler(original_query, updated_search_query, function_name)
			if function_name == "evaluate_resume_against_job_description":
				updated_search_query = arguments['resume']
				return function_handler(original_query, updated_search_query, function_name)

		return message.content
		