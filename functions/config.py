import json
import os

from config.consts import *

# Load config, can be local or not.
def load_config():
    local_config = CONFIG_LOCAL_PATH
    default_config = CONFIG_PATH

    if os.path.exists(local_config):
        config_file = local_config
        print(f"Using local configuration: {local_config}")
    elif os.path.exists(default_config):
        config_file = default_config
        print(f"Using default configuration: {default_config}")
    else:
        raise FileNotFoundError("Neither config-local.json nor config.json was found.")
    return AppConfig.from_json_file(config_file)


import json


class DiscordConfig:
    def __init__(self, token: str):
        self.token = token

    def __repr__(self):
        return f"DiscordConfig(token={self.token})"


class AppConfig:
    def __init__(self, discord: DiscordConfig, debug: bool):
        self.discord = discord
        self.debug = debug

    def __repr__(self):
        return f"AppConfig(discord={self.discord}, debug={self.debug})"

    @staticmethod
    def from_json_file(file_path: str):
        # Load JSON file
        with open(file_path, "r") as file:
            data = json.load(file)

        # Map JSON to classes
        discord_config = DiscordConfig(**data["discord"])
        return AppConfig(discord=discord_config, debug=data["debug"])


config = load_config()