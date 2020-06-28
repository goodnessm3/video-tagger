import json

# always load settings at import so they are available to other parts of the program
with open("settings.json", "r") as f:
    SETTINGS = json.load(f)


def save_settings():

    """The SETTINGS dict may have been changed by other parts of the program"""

    with open("settings.json", "w") as f:
        json.dump(SETTINGS, f)
