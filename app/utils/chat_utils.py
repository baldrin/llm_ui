def get_chat_title(messages):
    """Generate a simple title based on the first user message."""
    for msg in messages:
        if msg["role"] == "user":
            # Strip potential file attachment markers for cleaner titles
            content = msg["content"]
            if content.startswith("[Attached File:"):
                end_marker = "[End of File:"
                end_idx = content.find(end_marker)
                if end_idx != -1:
                    post_file_content = content[end_idx + len(end_marker):].split("\n", 1)[-1].strip()
                    content = post_file_content if post_file_content else "Chat with file"
            title = content[:30]
            return title + ("..." if len(content) > 30 else "")
    return "New Chat"

def generate_title_with_llm(messages, model_id, llm_service):
    """Generate a concise title using the LLM."""
    first_message = next((msg["content"] for msg in messages if msg["role"] == "user"), "")

    # Truncate if too long to save tokens
    first_message = first_message[:500] + "..." if len(first_message) > 500 else first_message

    system_prompt = """
        You are a title generator that creates short, concise titles.
        Rules:
        1. Create a 2-4 word title that captures the main topic
        2. Use plain text ONLY - no formatting, no markdown
        3. Do not use asterisks, equal signs, or other special characters
        4. Do not include the word "title" or any labels
        5. Do not include quotes around your answer
        6. Respond with ONLY the title text - nothing else

        Examples of good responses:
        "Python Snake Game"
        "Climate Change Analysis"
        "Recipe Recommendations"
    """

    prompt = [
        {"role": "system", "content": f"{system_prompt}"},
        {"role": "user", "content": first_message}
    ]
    
    try:
        response = llm_service.generate_completion(
            messages=prompt,
            stream=False,
            llm_model=model_id,
            max_tokens=10  # Keep it short
        )
        title = response.choices[0].message.content.strip()
        # Remove quotes if the LLM added them
        title = title.strip("\"'")
        print(f"title: {title}")
        return title if title else "New Chat"
    except Exception as e:
        print(f"Error generating title: {e}")
        return "New Chat"
