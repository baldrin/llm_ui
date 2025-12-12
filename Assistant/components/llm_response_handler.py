import streamlit as st
from typing import Dict, Optional, Any, List
from dataclasses import dataclass

from config.constants import DEFAULT_CHAT_TITLE
from config.config_loader import config
from config.exceptions import LLMError, ValidationError
from utils.chat.context_manager import context_manager
from utils.core.structured_logger import get_logger
from utils.core.session_utils import get_request_info
from utils.caching.cache_utils import invalidate_chat_caches
from services.message_processor import message_processor

logger = get_logger(__name__)


@dataclass
class LLMResponseResult:
    """Result from LLM response generation."""
    content: str
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    error: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        """Calculate total tokens used."""
        return self.input_tokens + self.output_tokens

    @property
    def billable_input_tokens(self) -> int:
        """Calculate billable input tokens (cache reads are cheaper)."""
        # Cache reads are typically 1/10th the cost of regular input tokens
        return self.input_tokens - self.cache_read_input_tokens


class LLMResponseHandler:
    """Handles LLM response generation with streaming and error handling."""

    def __init__(self):
        """Initialize the handler with current session state."""
        self.user_info = st.session_state.user_info
        self.llm_service = st.session_state.llm_service
        self.db_service = st.session_state.chat_service
        self.db_logger = st.session_state.db_logger

    def handle_response(self, available_llms_map: Dict[str, str]) -> None:
        """Main entry point for handling LLM response generation."""

        logger.info(
            "handle_response_entry",
            has_partial=("_streaming_partial_response" in st.session_state),
            partial_length=len(st.session_state.get("_streaming_partial_response", "")),
            is_generating=st.session_state.get("is_generating", False),
            stop_streaming=st.session_state.get("stop_streaming", False),
            save_partial_flag=st.session_state.get("save_partial_on_stop", False)
        )

        if self._recover_partial_response():
            return

        logger.info(
            "handle_response_called",
            is_generating=st.session_state.get("is_generating", False)
        )

        if not st.session_state.is_generating:
            logger.debug("handle_response_skipped_not_generating")
            return

        logger.info("starting_llm_generation")

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            self._show_thinking_state(message_placeholder)
            result = self._generate_response(
                available_llms_map,
                message_placeholder
            )

            # Save response even if partial (unless it was an error)
            if result.content and not result.error:
                self._save_response(result)
                self._update_title_if_needed()
            elif result.error:
                logger.error("response_had_error", error=result.error)

        was_stopped = st.session_state.get("stop_streaming", False)
        st.session_state.is_generating = False
        st.session_state.stop_streaming = False

        logger.info(
            "generation_completed",
            was_stopped=was_stopped,
            content_saved=bool(result.content and not result.error)
        )

        # Trigger rerun to update UI
        st.session_state.needs_rerun = True

    def _recover_partial_response(self) -> bool:
        """Attempt to recover and save partial response from interrupted generation."""
        if "_streaming_partial_response" not in st.session_state:
            return False

        partial_content = st.session_state._streaming_partial_response
        should_save = st.session_state.get("save_partial_on_stop", False)

        # Clean up flags
        if "_streaming_partial_response" in st.session_state:
            del st.session_state._streaming_partial_response
        if "save_partial_on_stop" in st.session_state:
            del st.session_state.save_partial_on_stop

        logger.info(
            "found_partial_response",
            length=len(partial_content),
            should_save=should_save
        )

        if not (partial_content and len(partial_content) > 0 and should_save):
            logger.warning(
                "partial_response_not_saved",
                has_content=bool(partial_content),
                should_save=should_save
            )
            return False

        # Save partial response
        result = LLMResponseResult(
            content=partial_content,
            input_tokens=0,
            output_tokens=len(partial_content) // 3.5, # (3.5 = ~characters per token for code)
            error=None
        )

        st.session_state.stop_streaming = True
        self._save_response(result)
        self._update_title_if_needed()

        logger.info("partial_response_saved_with_db_persistence")

        # Clean up
        st.session_state.is_generating = False
        st.session_state.stop_streaming = False
        st.session_state.needs_rerun = True

        return True

    def _show_thinking_state(self, message_placeholder) -> None:
        """Display initial 'thinking' animation."""
        with message_placeholder:
            st.markdown(
                """
                <div style="padding: 20px; text-align: center;">
                    <div style="font-size: 24px; margin-bottom: 10px;">🤔</div>
                    <div style="color: #666; font-size: 14px;">Thinking...</div>
                </div>
                """,
                unsafe_allow_html=True
            )

    def _generate_response(
        self, 
        available_llms_map: Dict[str, str], 
        message_placeholder
    ) -> LLMResponseResult:
        """Generate LLM response with error handling."""
        try:
            # Use message processor to prepare messages for LLM
            current_messages = st.session_state.chats[st.session_state.current_chat_id]["messages"]
            processed_messages = message_processor.prepare_messages_for_llm(current_messages)

            # Get current tokens for logging only (validation already done)
            current_tokens = context_manager.get_current_tokens(current_messages)

            logger.info(
                "generating_response",
                current_tokens=current_tokens,
                processed_message_count=len(processed_messages)
            )

            # Get model
            current_llm = st.session_state.selected_llm
            llm_model = available_llms_map.get(current_llm)

            if not llm_model:
                raise ValidationError(
                    "Invalid LLM model selected",
                    details={"selected_model": current_llm}
                )

            # Generate response with pre-processed messages
            response_stream = self.llm_service.generate_completion(
                messages=processed_messages,
                stream=True,
                llm_model=llm_model,
                temperature=config.get('llm.temperature', 0.3),
                max_tokens=config.get('llm.max_tokens', 4096)
            )

            # Display streaming response
            content, usage = self._display_streaming_response(
                response_stream, 
                message_placeholder
            )

            input_tokens_final = current_tokens  # fallback to estimate
            output_tokens_final = 0
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

            if usage:
                if isinstance(usage, dict):
                    # Response API format. Try both field names
                    input_tokens_final = usage.get('prompt_tokens', 
                                         usage.get('input_tokens', current_tokens))
                    output_tokens_final = usage.get('completion_tokens',
                                          usage.get('output_tokens', 0))
                    cache_creation_input_tokens = usage.get('cache_creation_input_tokens', 0)
                    cache_read_input_tokens = usage.get('cache_read_input_tokens', 0)
                else:
                    # Chat Completions API format (object)
                    input_tokens_final = getattr(usage, 'prompt_tokens',
                                                getattr(usage, 'input_tokens', current_tokens))
                    output_tokens_final = getattr(usage, 'completion_tokens',
                                                getattr(usage, 'output_tokens', 0))
                    cache_creation_input_tokens = getattr(usage, 'cache_creation_input_tokens', 0)
                    cache_read_input_tokens = getattr(usage, 'cache_read_input_tokens', 0)

            # Check if it was stopped
            was_stopped = st.session_state.get("stop_streaming", False)

            if was_stopped:
                logger.info(
                    "partial_response_generated",
                    input_tokens=input_tokens_final,
                    output_tokens=output_tokens_final,
                    cache_creation_input_tokens=cache_creation_input_tokens,
                    cache_read_input_tokens=cache_read_input_tokens,
                    content_length=len(content)
                )

            return LLMResponseResult(
                content=content,
                input_tokens=input_tokens_final,
                output_tokens=output_tokens_final,
                cache_creation_input_tokens=cache_creation_input_tokens,
                cache_read_input_tokens=cache_read_input_tokens,
                error=None
            )

        except LLMError as e:
            logger.error(
                "llm_error",
                error=str(e)
            )
            message_placeholder.error(f"🤖 {e.message}")

            if st.button("🔄 Retry", key="retry_llm"):
                st.session_state.is_generating = True
                st.session_state.needs_rerun = True

            return LLMResponseResult(
                content=f"Error: {e.message}",
                input_tokens=0,
                output_tokens=0,
                error=str(e)
            )

        except Exception as e:
            logger.error(
                "unexpected_response_error",
                error=str(e)
            )
            message_placeholder.error(
                "An unexpected error occurred while generating the response."
            )
            if config.is_development():
                st.exception(e)

            return LLMResponseResult(
                content="Sorry, an unexpected error occurred while generating the response.",
                input_tokens=0,
                output_tokens=0,
                error=str(e)
            )

    def _display_streaming_response(
        self,
        response_stream,
        message_placeholder
    ) -> tuple[str, Optional[Any]]:
        """Display streaming response with cursor animation and incremental saving."""

        # Handle non-streaming response
        if hasattr(response_stream, 'choices'):
            content = response_stream.choices[0].message.content
            formatted_content = f"\n\n{content}\n"
            message_placeholder.markdown(formatted_content)
            usage = getattr(response_stream, 'usage', None)
            return content, usage

        full_response = ""
        final_usage = None

        # Initialize partial response in session state
        st.session_state._streaming_partial_response = ""

        try:
            for chunk in response_stream:
                # Extract usage from the chunk
                if hasattr(chunk, 'usage') and chunk.usage:
                    # Convert to dict for consistent handling
                    if isinstance(chunk.usage, dict):
                        final_usage = chunk.usage
                    else:
                        # Convert object to dict
                        final_usage = {
                            'input_tokens': getattr(chunk.usage, 'prompt_tokens', 0),
                            'output_tokens': getattr(chunk.usage, 'completion_tokens', 0),
                            'cache_creation_input_tokens': getattr(chunk.usage, 'cache_creation_input_tokens', 0),
                            'cache_read_input_tokens': getattr(chunk.usage, 'cache_read_input_tokens', 0)
                        }

                # Check stop flag
                if st.session_state.get("stop_streaming", False):
                    logger.warning(
                        "streaming_stopped_by_user",
                        partial_length=len(full_response),
                        chat_id=st.session_state.current_chat_id
                    )
                    break

                # Extract content
                if (chunk.choices and 
                    chunk.choices[0].delta and 
                    hasattr(chunk.choices[0].delta, 'content')):
                    content = chunk.choices[0].delta.content
                    if content:
                        full_response += content
                        st.session_state._streaming_partial_response = full_response
                        formatted_streaming = f"\n\n{full_response}▌\n"
                        message_placeholder.markdown(formatted_streaming)

        except Exception as e:
            logger.error(
                "streaming_loop_error",
                error=str(e),
                partial_length=len(full_response)
            )

        # Check if stopped
        was_stopped = st.session_state.get("stop_streaming", False)

        # Display final content
        formatted_final = f"\n\n{full_response}\n"
        message_placeholder.markdown(formatted_final)

        # Only clean up partial if completed normally
        if not was_stopped and "_streaming_partial_response" in st.session_state:
            del st.session_state._streaming_partial_response

        return full_response, final_usage

    def _save_response(self, result: LLMResponseResult) -> None:
        """Save response to database and log activity."""
        try:
            was_stopped = st.session_state.get("stop_streaming", False)

            # Save clean content without marker
            formatted_content = f"\n{result.content}\n"

            assistant_message = {
                "role": "assistant",
                "content": formatted_content,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cache_creation_input_tokens": result.cache_creation_input_tokens,
                "cache_read_input_tokens": result.cache_read_input_tokens,
                "was_stopped": was_stopped
            }

            current_chat_id = st.session_state.current_chat_id

            # Add to session state
            st.session_state.chats[current_chat_id]["messages"].append(assistant_message)

            # Save to database with extended token info
            message_id = self.db_service.save_message(
                user_id=self.user_info.get("user_id"),
                chat_id=current_chat_id,
                role="assistant",
                content=formatted_content,
                llm_model=st.session_state.selected_llm,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cache_creation_input_tokens=result.cache_creation_input_tokens,
                cache_read_input_tokens=result.cache_read_input_tokens
            )

            # Log activity with detailed token breakdown
            # Log activity with detailed token breakdown
            request_info = get_request_info()
            self.db_logger.log_message(
                user_id=self.user_info.get("user_id"),
                message_id=message_id,
                message_type="assistant",
                chat_id=current_chat_id,
                selected_llm=st.session_state.selected_llm,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cache_creation_input_tokens=result.cache_creation_input_tokens,
                cache_read_input_tokens=result.cache_read_input_tokens,
                user_name=self.user_info.get("user_name"),
                user_email=self.user_info.get("user_email"),
                session_id=st.session_state.session_id,
                ip_address=request_info.get("ip_address"),
                user_agent=request_info.get("user_agent")
            )

            # Invalidate caches
            invalidate_chat_caches(current_chat_id)

            logger.info(
                "response_saved_with_token_details",
                message_id=message_id,
                chat_id=current_chat_id,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cache_creation_input_tokens=result.cache_creation_input_tokens,
                cache_read_input_tokens=result.cache_read_input_tokens,
                was_stopped=was_stopped
            )

        except Exception as e:
            logger.error(
                "response_save_failed",
                error=str(e),
                chat_id=st.session_state.current_chat_id
            )
            st.error("Failed to save response to database.")

    def _update_title_if_needed(self) -> None:
        """Update chat title if it's still the default."""
        try:
            current_chat_id = st.session_state.current_chat_id
            chat = st.session_state.chats[current_chat_id]

            # Only update if title is still default
            if chat.get("title") == DEFAULT_CHAT_TITLE:
                messages = chat.get("messages", [])

                # Need at least one user message to generate title
                if len(messages) >= 1:
                    from utils.chat.chat_utils import get_chat_title

                    new_title = get_chat_title(messages)

                    # Update in session state
                    chat["title"] = new_title

                    # Queue database update
                    self.db_service.update_chat_title(
                        user_id=self.user_info.get("user_id"),
                        chat_id=current_chat_id,
                        title=new_title
                    )

                    logger.info(
                        "chat_title_updated",
                        chat_id=current_chat_id,
                        new_title=new_title
                    )

        except Exception as e:
            logger.error(
                "title_update_failed",
                error=str(e),
                chat_id=st.session_state.current_chat_id
            )

def handle_llm_response(available_llms_map: Dict[str, str]) -> None:
    """Main entry point for handling LLM response generation."""
    if not st.session_state.get("is_generating", False):
        return

    handler = LLMResponseHandler()
    handler.handle_response(available_llms_map)