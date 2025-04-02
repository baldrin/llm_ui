import importlib

class PluginManager:
    def __init__(self, plugin_folder='plugins'):
        self.plugin_folder = plugin_folder
        self.plugins = {}

    def load_plugins(self):
        for file in os.listdir(self.plugin_folder):
            if file.endwith('.py'):
                module_name = file[:-3]
                module = importlib.import_module(f'{self.plugin_folder}.{module_name}')
                self.plugins[module_name] = module

    def get_plugin(self, name):
        return self.plugins.get(name)
