def calculate_tokens(text):
    """Estimate the number of tokens in a text string."""
    return len(text) // 4

def calculate_cost(tokens, type="input"):
    """Calculate approximate cost based on token count and type."""
    cost_per_million = 3 if type == "input" else 15
    return (tokens / 1_000_000) * cost_per_million
