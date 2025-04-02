import json

def load_config():
    with open('config/config.json') as f:
        return json.load(f)
