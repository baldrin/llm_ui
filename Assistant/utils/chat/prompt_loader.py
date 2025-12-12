from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime
import re
import streamlit as st

from config.config_loader import config
from utils.core.structured_logger import get_logger

logger = get_logger(__name__)


class PromptLoader:
    """
    Loads and processes prompt templates from markdown files.
    Supports variable substitution with {variable} syntax.
    """

    def __init__(self):
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent
        self.prompts_dir = project_root / "prompts"
        
        self._cache: Dict[str, str] = {}
        self._ensure_prompts_directory()

    def _ensure_prompts_directory(self) -> None:
        """Ensure prompts directory exists."""
        if not self.prompts_dir.exists():
            logger.warning(
                "prompts_directory_missing",
                path=str(self.prompts_dir),
                message="Creating prompts directory"
            )
            self.prompts_dir.mkdir(exist_ok=True)

    def load_prompt(
        self, 
        filename: str, 
        variables: Optional[Dict[str, Any]] = None,
        use_cache: bool = True
    ) -> str:
        """Load a prompt from file with variable substitution."""
        if not filename.endswith('.md'):
            filename += '.md'

        cache_key = filename

        # Try cache first
        if use_cache and cache_key in self._cache:
            raw_content = self._cache[cache_key]
            logger.debug("prompt_loaded_from_cache", filename=filename)
        else:
            raw_content = self._load_from_file(filename)
            if raw_content and use_cache:
                self._cache[cache_key] = raw_content

        # Apply variable substitution
        if variables:
            processed_content = self._substitute_variables(raw_content, variables)
        else:
            processed_content = raw_content

        logger.debug(
            "prompt_loaded",
            filename=filename,
            content_length=len(processed_content),
            variables_count=len(variables) if variables else 0
        )

        return processed_content

    def _load_from_file(self, filename: str) -> str:
        """Load prompt content from file with error handling."""
        file_path = self.prompts_dir / filename
        

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            logger.debug(
                "prompt_file_loaded",
                filename=filename,
                path=str(file_path),
                content_length=len(content)
            )

            return content

        except FileNotFoundError:
            logger.error(
                "prompt_file_not_found",
                filename=filename,
                path=str(file_path),
                message="Prompt file missing - returning empty string"
            )
            return ""

        except UnicodeDecodeError as e:
            logger.error(
                "prompt_file_encoding_error",
                filename=filename,
                path=str(file_path),
                error=str(e),
                message="File encoding error - returning empty string"
            )
            return ""

        except Exception as e:
            logger.error(
                "prompt_file_load_error",
                filename=filename,
                path=str(file_path),
                error=str(e),
                message="Unexpected error loading prompt file"
            )
            return ""

    def _substitute_variables(self, content: str, variables: Dict[str, Any]) -> str:
        """Substitute variables in content using {variable} syntax."""
        if not content or not variables:
            return content

        processed_content = content
        substitutions_made = 0

        for var_name, var_value in variables.items():
            placeholder = f"{{{var_name}}}"
            if placeholder in processed_content:
                processed_content = processed_content.replace(placeholder, str(var_value))
                substitutions_made += 1

        # Check for unsubstituted variables
        remaining_vars = re.findall(r'\{(\w+)\}', processed_content)
        if remaining_vars:
            logger.warning(
                "unsubstituted_variables_found",
                variables=remaining_vars,
                message="Some template variables were not substituted"
            )

        logger.debug(
            "variables_substituted",
            substitutions_made=substitutions_made,
            remaining_variables=len(remaining_vars)
        )

        return processed_content

    def get_system_prompt(self, **variables) -> str:
        """Load the main system prompt with common variables."""
        prompt_file = config.get('llm.system_prompt_file', 'system_prompt.md')

        common_vars = self._get_common_variables()
        common_vars.update(variables)

        return self.load_prompt(prompt_file, common_vars)

    def get_title_generation_prompt(self, **variables) -> str:
        """Load the title generation prompt."""
        prompt_file = config.get('title_generation.title_generation_prompt_file', 'title_generation_prompt.md')

        common_vars = self._get_common_variables()
        common_vars.update(variables)

        return self.load_prompt(prompt_file, common_vars)

    def _get_common_variables(self) -> Dict[str, str]:
        """Get common variables available to all prompts."""
        model_name = st.session_state.selected_llm
        
        if not model_name:
            model_name = 'AI Assistant'

        return {
            'current_date': datetime.now().strftime('%Y-%m-%d'),
            'model_name': model_name,
        }

    def clear_cache(self) -> None:
        """Clear the prompt cache."""
        self._cache.clear()
        logger.debug("prompt_cache_cleared")


# Global instance
prompt_loader = PromptLoader()

# Convenience functions
def load_prompt(filename: str, variables: Optional[Dict[str, Any]] = None) -> str:
    """Load a prompt file with variable substitution."""
    return prompt_loader.load_prompt(filename, variables)

def get_system_prompt(**variables) -> str:
    """Get the main system prompt with variables."""
    return prompt_loader.get_system_prompt(**variables)

def get_title_generation_prompt(**variables) -> str:
    """Get the title generation prompt with variables."""
    return prompt_loader.get_title_generation_prompt(**variables)