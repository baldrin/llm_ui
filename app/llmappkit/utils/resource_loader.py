def load_resource(resource_name):
    with open(f'resources/{resource_name}.txt') as f:
        return f.read()
