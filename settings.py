import json

# always load settings at import so they are available to other parts of the program
with open("settings.json", "r") as f:
    SETTINGS = json.load(f)

DELETION_WHITELIST = []  # when running the "free space" command, can only look in here for videos to delete
with open("deletion_whitelist.txt", "r") as f:
    for line in f.readlines():
        DELETION_WHITELIST.append(line.rstrip("\r\n"))

def save_settings():

    """The SETTINGS dict may have been changed by other parts of the program"""

    with open("settings.json", "w") as f:
        json.dump(SETTINGS, f)
