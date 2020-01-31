from tkinter import *
from PIL import Image
from io import BytesIO
import os
import subprocess as sp
from settings import SETTINGS
from random import randint

FFMPEG = SETTINGS["FFMPEG_PATH"]
FFPROBE = SETTINGS["FFPROBE_PATH"]


class VideoObject:

    """Container for information about a video file. Generates thumbnails with ffmpeg and stores them, also
    gets general info like duration, resolution, etc, to be made available to the main program."""

    def __init__(self, full_path):

        self.path = full_path
        filename = os.path.split(self.path)[1]
        self.filename = filename.rstrip("\"")  # filename final quote mark stripped off
        self.duration, self.increment = self.get_initial_info(self.path)
        if self.duration is not None:
            # if it's none then this video has broken ffmpeg
            self.time_points = self.get_time_points()
            self.images = self.get_thumbnails(self.time_points)

    def refine(self):

        """apply a small delta to the thumbnail time points to get different images"""

        tp = self.get_time_points()
        tp2 = [randint(-5, 5) + x for x in tp]
        # check to make sure the random addition hasn't put the time outside of the video length
        if tp2[0] < 0:
            tp2[0] = 0.1
        if tp2[-1] > self.duration:
            tp2[-1] = self.duration - 1
        self.time_points = tp2
        self.images = self.get_thumbnails(self.time_points)

    @staticmethod
    def get_initial_info(path):

        cmd = f'''{FFPROBE} -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{path}"'''
        pipe = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, bufsize=10 ** 8)
        try:
            info2, error = pipe.communicate(timeout=15)
            info = info2.decode("utf-8")
        except sp.TimeoutExpired:
            print("ffmpeg timed out getting info")
            pipe.kill()
            return None, None
        try:
            duration = float(info)
        except:
            print("error getting video info")
            print(error)
            return None, None

        increment = duration / 10.0

        return duration, increment

    def get_thumbnails(self, times):

        """returns a list of gif images at the times given"""

        def get_image(timepoint):

            cmd = f'''{FFMPEG} -ss {timepoint} -i "{self.path}" -f image2pipe -vframes 1 -s 320x240 -'''
            pipe = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, bufsize=10 ** 8)

            return pipe

        images_to_return = []

        for i in times:
            # it seems inefficient to load up ffmpeg multiple times but this allows direct seeking
            # to the desired time point. By using the fps filter with a fractional number, the
            # images can be got with one call to ffmpeg but it's much slower and CPU intensive
            # as the entire video must be decoded rather than seeking by keyframe.
            data = get_image(i)
            try:
                imagedata2 = data.communicate(timeout=15)
            except sp.TimeoutExpired:
                print("ffmpeg timed out getting thumbnails")
                data.kill()
                return []
            imagedata = imagedata2[0]
            flo = BytesIO(imagedata)
            try:
                image = Image.open(flo)
            except:
                print("error opening image")
                print(imagedata2[1])  # print ffmpeg's stderr to the console
                return []
            images_to_return.append(image)

        return images_to_return

    def get_time_points(self):

        """returns 9 time points within self.duration, evenly spread with no other arguments or centred around time"""

        a = 0.1
        times = []

        while len(times) < 9:
            times.append(a)
            a += self.increment

            if a > self.duration:
                print("time beyond video end, truncating")
                a -= self.increment

        return times

    @staticmethod
    def get_video_res(fullpath):

        cmd = f'''{FFPROBE} -v error -select_streams v:0 -show_entries stream=height,width -of csv=s=x:p=0 {fullpath}'''
        pipe = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, bufsize=10 ** 8)
        info2, error = pipe.communicate()
        info = info2.decode("utf-8")
        return info.rstrip("\r\n")
