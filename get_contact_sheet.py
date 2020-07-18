from videoobject import VideoObject
from sys import argv
import os

"""Standalone script to be invoked from the command line, prints a contact sheet for a video using VideoObject."""

directory = argv[1]
targets = os.listdir(directory)
thumbs = int(argv[2])
for x in targets:
    vo = VideoObject(os.path.join(directory, x), thumbs)
    vo.write_contact_sheet(argv[1])
