import json
import os

from gi.repository import GLib

APP_ID = "io.github.albertosusco.Draggo"
APP_NAME = "Draggo"
VERSION = "1.0.0"
WEBSITE = "https://github.com/albertosusco/draggo"

DATA_DIR = os.path.join(GLib.get_user_data_dir(), "draggo")
CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "draggo")
SHELF_FILE = os.path.join(DATA_DIR, "shelf.json")
FILES_DIR = os.path.join(DATA_DIR, "files")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

DEFAULTS = {
    "remove-after-drag": True,
    "persist": True,
}


class Settings:
    def __init__(self, path=SETTINGS_FILE):
        self.path = path
        self.values = dict(DEFAULTS)
        try:
            with open(path, encoding="utf-8") as f:
                stored = json.load(f)
            self.values.update({k: v for k, v in stored.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

    def __getitem__(self, key):
        return self.values[key]

    def __setitem__(self, key, value):
        self.values[key] = value
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.values, f, indent=1)
