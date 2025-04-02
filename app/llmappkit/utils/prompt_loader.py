def load_prompt(prompt_name):
    with open(f'prompts/{prompt_name}.txt') as f:
        return f.read()
