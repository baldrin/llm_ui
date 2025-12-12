"""
Message processor for handling chat messages and attachments.
"""
from typing import List, Dict, Any

from config.types import MessageDict
from utils.core.structured_logger import get_logger
from utils.content.file_handler import format_file_content
from utils.content.image_encoder import ImageEncoder
from utils.content.pdf_handler import pdf_handler
from utils.chat.prompt_loader import prompt_loader

logger = get_logger(__name__)


class MessageProcessor:
    """Handles all message processing for chat display and LLM consumption."""

    def __init__(self):
        """Initialize the message processor."""
        self.image_encoder = ImageEncoder()
        logger.debug("message_processor_initialized")

    def prepare_messages_for_llm(self, messages: List[MessageDict]) -> List[Dict[str, Any]]:
        """Prepare messages for LLM consumption with attachments in original positions."""
        logger.debug(
            "preparing_messages_for_llm",
            message_count=len(messages)
        )

        # Add system prompt
        system_prompt = prompt_loader.get_system_prompt()
        llm_messages = []

        if system_prompt:
            llm_messages.append({
                "role": "system",
                "content": system_prompt
            })

        # Process each message and embed attachments where they belong
        for msg in messages:
            processed_msg = self._process_message_with_attachments(msg)
            llm_messages.append(processed_msg)

        logger.info(
            "messages_prepared_for_llm",
            total_messages=len(llm_messages),
            user_messages=len([m for m in llm_messages if m.get("role") == "user"]),
            messages_with_attachments=len([m for m in messages if "attachments" in m])
        )

        return llm_messages

    def _process_message_with_attachments(self, message: MessageDict) -> Dict[str, Any]:
        """Process a single message and embed its attachments."""
        processed_msg = {
            "role": message["role"],
            "content": message["content"]
        }

        # Only process attachments for user messages
        if message.get("role") != "user" or "attachments" not in message:
            return processed_msg

        attachments = message["attachments"]

        logger.debug(
            "processing_message_attachments",
            has_text_files=bool(attachments.get("text_files")),
            text_file_count=len(attachments.get("text_files", [])),
            has_images=bool(attachments.get("images")),
            image_count=len(attachments.get("images", [])),
            has_pdfs=bool(attachments.get("pdfs")),
            pdf_count=len(attachments.get("pdfs", []))
        )

        # Start with text content
        if isinstance(processed_msg["content"], str):
            content_parts = [{"type": "text", "text": processed_msg["content"]}]
        else:
            content_parts = processed_msg["content"].copy()

        # Prepend text files to message content (for LLM context)
        if attachments.get("text_files"):
            text_content_parts = []
            for text_file in attachments["text_files"]:
                file_html = format_file_content(text_file['name'], text_file['content'])
                text_content_parts.append(file_html)

            if text_content_parts:
                # Combine text files with original message
                combined_text = "\n\n".join(text_content_parts) + "\n\n" + content_parts[0]["text"]
                content_parts[0]["text"] = combined_text

                logger.debug(
                    "text_files_embedded",
                    file_count=len(attachments["text_files"]),
                    combined_length=len(combined_text)
                )

        # Add images as structured content
        if attachments.get("images"):
            for idx, img in enumerate(attachments["images"]):
                try:
                    base64_image, image_format = self.image_encoder.encode_image(img)
                    media_type = "image/png" if image_format == "PNG" else "image/jpeg"

                    content_parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{base64_image}"
                        }
                    })

                    logger.debug(
                        "image_embedded",
                        image_index=idx,
                        format=image_format,
                        size_kb=len(base64_image) / 1024
                    )

                except Exception as e:
                    logger.error(
                        "image_embedding_failed",
                        image_index=idx,
                        error=str(e)
                    )

        # Add PDFs as structured content
        if attachments.get("pdfs"):
            for idx, pdf_bytes in enumerate(attachments["pdfs"]):
                try:
                    base64_pdf = pdf_handler.encode_pdf(pdf_bytes)

                    content_parts.append({
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": base64_pdf
                        }
                    })

                    logger.debug(
                        "pdf_embedded",
                        pdf_index=idx,
                        size_kb=len(base64_pdf) / 1024
                    )

                except Exception as e:
                    logger.error(
                        "pdf_embedding_failed",
                        pdf_index=idx,
                        error=str(e)
                    )

        processed_msg["content"] = content_parts

        logger.info(
            "message_processed_with_attachments",
            content_parts=len(content_parts),
            text_files=len(attachments.get("text_files", [])),
            images=len(attachments.get("images", [])),
            pdfs=len(attachments.get("pdfs", []))
        )

        return processed_msg

    def build_user_message_content(self, prompt: str, attachments: Dict[str, List[Any]]) -> str:
        """Build user message content with attachment indicators for display."""
        message_content = prompt

        # Add attachment indicators (for display only)
        if attachments.get('text_files'):
            file_names = [f['name'] for f in attachments['text_files']]
            message_content = f"📄 **Text files attached:** {', '.join(file_names)}\n\n{message_content}"

        if attachments.get('images'):
            image_names = [img['name'] for img in attachments['images']]
            message_content = f"🖼️ **Images attached:** {', '.join(image_names)}\n\n{message_content}"

        if attachments.get('pdfs'):
            pdf_info = [f"{pdf['name']} ({pdf['pages']} pages)" for pdf in attachments['pdfs']]
            message_content = f"📄 **PDFs attached:** {', '.join(pdf_info)}\n\n{message_content}"

        logger.debug(
            "user_message_content_built",
            original_length=len(prompt),
            final_length=len(message_content),
            has_text_files=bool(attachments.get('text_files')),
            has_images=bool(attachments.get('images')),
            has_pdfs=bool(attachments.get('pdfs'))
        )

        return message_content


# Global instance for easy imports
message_processor = MessageProcessor()