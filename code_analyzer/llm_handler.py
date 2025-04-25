import litellm
import logging
import os
from litellm import completion, RateLimitError, APIConnectionError, Timeout
import json

logger = logging.getLogger(__name__)

# Global variable to store the configured model name
_LLM_MODEL = None

def set_llm_model(model_name):
    """Sets the LLM model to be used by LiteLLM."""
    global _LLM_MODEL
    _LLM_MODEL = model_name
    logger.info(f"LiteLLM configured to use model: {_LLM_MODEL}")
    # Optional: Add validation here if needed to check if model is supported by LiteLLM or configured providers

def get_llm_analysis(filepath, content, language, timeout=300):
    """
    Uses LiteLLM to get analysis for the given code content.

    Args:
        filepath (str): The path to the file (for context).
        content (str): The source code content.
        language (str): The detected language of the code.
        timeout (int): Timeout in seconds for the API call.

    Returns:
        dict: A dictionary containing the analysis (summary, key_elements, issues, suggestions)
              or an error message.
    """
    global _LLM_MODEL
    if not _LLM_MODEL:
        raise ValueError("LLM model has not been set. Call set_llm_model() first.")
        
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("GEMINI_API_KEY") and "VERTEX" not in _LLM_MODEL: # Add other checks as needed
        logger.warning("No common API key found in environment variables (e.g., OPENAI_API_KEY). LLM calls might fail if not configured otherwise (e.g., config.yaml).")


    prompt = f"""
Analyze the following source code file:
File Path: {filepath}
Detected Language: {language}

File Content:
{content}

Provide the following analysis in clear sections:

1.  **Summary**: Briefly describe the purpose and main functionality of this file.
2.  **Key Functions/Procedures**: Identify the most important functions, methods, or procedures. Explain what each one does in simple terms. If none are present (e.g., config file), state that.
3.  **Potential Issues & Legacy Constructs**: Point out any potential issues like:
    *   Outdated libraries or practices.
    *   Complex logic or "code smells".
    *   Lack of error handling.
    *   Hardcoded values that should be configuration.
    *   Possible security vulnerabilities (be general, don't claim exploits).
    *   Any obvious technical debt indicators.
4.  **Modernization Suggestions**: Offer high-level ideas for improving or modernizing this code. Examples:
    *   Refactoring opportunities.
    *   Replacing legacy components with modern alternatives.
    *   Possibility of rewriting as a microservice/API.
    *   Improving testability.
    *   Adopting standard design patterns.

Format your response clearly using markdown headings for each section (e.g., `### Summary`). Be concise but informative. If the file is not code (e.g., plain text, config), describe its likely role.
"""

    messages = [{"role": "user", "content": prompt}]

    try:
        logger.debug(f"Sending request to LLM ({_LLM_MODEL}) for file: {filepath}")
        response = completion(
            model=_LLM_MODEL,
            messages=messages,
            temperature=0.2, # Lower temperature for more factual analysis
            max_tokens=1500, # Adjust as needed based on model and desired detail
            timeout=timeout,
            drop_params=True,
            # Add other parameters like specific API keys if not using environment variables
            # api_key=os.getenv("SPECIFIC_KEY_IF_NEEDED")
        )

        analysis_text = response.choices[0].message.content
        logger.debug(f"Received LLM response for {filepath}")
        print("\nLLM Analysis:")
        print(analysis_text)
        print("\n")

        # Simple parsing based on expected markdown headings (can be improved)
        analysis_data = {
            "summary": "Not found in response.",
            "key_elements": "Not found in response.",
            "issues": "Not found in response.",
            "suggestions": "Not found in response.",
            "raw_text": analysis_text # Keep raw text for display
        }

        # Basic parsing attempt (can be made more robust)
        sections = {
            "summary": "### Summary",
            "key_elements": "### Key Functions/Procedures",
            "issues": "### Potential Issues & Legacy Constructs",
            "suggestions": "### Modernization Suggestions"
        }
        
        current_section = None
        parsed_content = {}

        lines = analysis_text.splitlines()
        for line in lines:
            line_stripped = line.strip()
            found_section = None
            for key, heading in sections.items():
                 # Match heading ignoring leading/trailing whitespace and potential markdown variations
                if line_stripped.startswith(heading):
                    current_section = key
                    parsed_content[current_section] = "" # Initialize section
                    found_section = True
                    # Optional: Remove heading from the content itself
                    # content_start_index = line.find(heading) + len(heading)
                    # line_content = line[content_start_index:].strip()
                    # if line_content:
                    #    parsed_content[current_section] += line_content + "\n"
                    break # Found the heading for this line
            
            if not found_section and current_section:
                 # Append line to the current section, preserving original indentation/formatting somewhat
                parsed_content[current_section] += line + "\n"

        # Update analysis_data with parsed content if found
        for key in analysis_data:
            if key in parsed_content and key != "raw_text":
                 # Trim leading/trailing whitespace from the extracted section
                 analysis_data[key] = parsed_content[key].strip() if parsed_content[key] else "No specific points mentioned."


        return analysis_data

    except RateLimitError as e:
        logger.error(f"LLM Rate Limit Error for {filepath}: {e}")
        return {"error": f"Rate limit exceeded. Please wait and try again. Details: {e}"}
    except APIConnectionError as e:
        logger.error(f"LLM API Connection Error for {filepath}: {e}")
        return {"error": f"Could not connect to the LLM API. Check network/config. Details: {e}"}
    except Timeout as e:
        logger.error(f"LLM Timeout Error for {filepath} after {timeout}s: {e}")
        return {"error": f"LLM request timed out after {timeout} seconds. Details: {e}"}
    except Exception as e:
        # Catch other potential errors from LiteLLM or the API
        logger.error(f"LLM General Error for {filepath}: {e}", exc_info=True)
        # Check for specific common errors if possible (e.g., authentication, invalid model)
        error_str = str(e)
        if "authentication" in error_str.lower():
             return {"error": f"LLM authentication failed. Check API key. Details: {e}"}
        if "invalid model" in error_str.lower():
             return {"error": f"Invalid LLM model specified: {_LLM_MODEL}. Details: {e}"}
        return {"error": f"An unexpected error occurred during LLM analysis: {e}"}
    
def get_project_summary_analysis(analysis_results, dir_structure, timeout=300, max_files_for_context=10):
    """
    Uses LiteLLM to generate a project-level summary based on aggregated data.

    Args:
        analysis_results (list): List of file analysis dictionaries.
        dir_structure (dict): The directory structure.
        timeout (int): Timeout in seconds for the API call.
        max_files_for_context (int): Max number of individual file summaries to include in the prompt.

    Returns:
        str: The generated project summary text (Markdown formatted) or an error message string.
    """
    global _LLM_MODEL
    if not _LLM_MODEL:
        logger.error("Cannot generate project summary: LLM model not set.")
        return "Error: LLM model not configured."

    if not analysis_results:
        logger.warning("Cannot generate project summary: No analysis results available.")
        return "Project appears to be empty or no files were analyzed."

    # --- Prepare data for the prompt ---
    total_files = len(analysis_results)
    code_files = [f for f in analysis_results if f['is_code']]
    code_files_count = len(code_files)
    llm_analyzed_files = [f for f in code_files if f.get('llm_analysis') and not f.get('llm_skipped') and 'error' not in f.get('llm_analysis')]

    if not llm_analyzed_files:
        logger.warning("Cannot generate project summary: No individual file analyses available for context.")
        return "Insufficient data for project summary (no files were successfully analyzed by LLM)."

    # Language distribution
    lang_counts = {}
    total_lines = 0
    for f in analysis_results:
        lang = f.get('language', 'Unknown')
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
        total_lines += f.get('line_count', 0)
    # Sort languages by count desc
    sorted_langs = sorted(lang_counts.items(), key=lambda item: item[1], reverse=True)

    # Select representative file summaries (e.g., largest analyzed code files)
    llm_analyzed_files.sort(key=lambda f: f.get('size', 0), reverse=True)
    sample_files_context = []
    for i, file_info in enumerate(llm_analyzed_files):
        if i >= max_files_for_context:
            break
        # Include path and the 'summary' part of its analysis
        summary_text = file_info['llm_analysis'].get('summary', 'Summary not available.')
        # Limit length of each summary to avoid excessive prompt size
        max_summary_len = 300
        if len(summary_text) > max_summary_len:
            summary_text = summary_text[:max_summary_len] + "..."
            
        sample_files_context.append({
            "path": file_info.get('relative_path', 'N/A'),
            "summary": summary_text
        })

    # Simplified directory structure (top-level items)
    top_level_items = [child['name'] + ('/' if child['type'] == 'directory' else '') for child in dir_structure.get('children', [])]

    # --- Construct the prompt ---
    prompt = f"""
Analyze the provided information about a software project and generate a concise, high-level project summary suitable for a README file. Focus *only* on the data given.

**Project Metadata:**
*   Total Files: {total_files}
*   Code Files: {code_files_count}
*   Total Lines (approx): {total_lines}
*   Detected Languages (files): {json.dumps(dict(sorted_langs), indent=2)}
*   Top-Level Structure: {', '.join(top_level_items) if top_level_items else 'N/A'}

**Summaries from Representative Code Files (Max {max_files_for_context}):**
{json.dumps(sample_files_context, indent=2)}

**Task:**
Based *solely* on the metadata and file summaries above, provide a project overview covering:
1.  **Overall Purpose:** What does the project likely do?
2.  **Technologies:** What are the predominant languages/technologies apparent from the data?
3.  **Scale & Complexity:** Give a brief assessment of its size/complexity.
4.  **Structure/Architecture Hints:** Any obvious structural patterns or components suggested by the data? (Be cautious, state if unclear).
5.  **Potential Themes:** Are there any recurring themes visible *just from the provided file summaries* (e.g., common purpose, potential issues mentioned)?

Format the output using Markdown. Be objective and stick to the provided information. If the information is insufficient for a point, state that clearly.
"""

    messages = [{"role": "user", "content": prompt}]

    try:
        logger.info(f"Requesting project summary from LLM ({_LLM_MODEL})...")
        response = completion(
            model=_LLM_MODEL,
            messages=messages,
            temperature=0.3, # Slightly higher temp for synthesis
            max_tokens=800, # Allow decent length for summary
            timeout=timeout,
            drop_params=True,
        )

        summary_text = response.choices[0].message.content
        logger.info(f"Received project summary from LLM.")
        return summary_text

    except Exception as e:
        logger.error(f"LLM Project Summary Error: {e}", exc_info=True)
        # Check for specific common errors if possible
        error_str = str(e)
        if isinstance(e, RateLimitError):
            return f"Error: Rate limit exceeded while generating project summary. {e}"
        if isinstance(e, APIConnectionError):
             return f"Error: Could not connect to the LLM API for project summary. {e}"
        if isinstance(e, Timeout):
             return f"Error: LLM request timed out during project summary generation. {e}"
        if "authentication" in error_str.lower():
             return f"Error: LLM authentication failed for project summary. Check API key. {e}"
        return f"Error: An unexpected error occurred during project summary generation: {e}"