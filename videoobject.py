from tkinter import *
from PIL import Image
from io import BytesIO
import os
import subprocess as sp


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

    def refine(self, timepoint, coarse=False, index=4):

        self.time_points = self.get_time_points(timepoint, coarse, index)
        self.images = self.get_thumbnails(self.time_points)

    @staticmethod
    def get_initial_info(path):

        path = '''"{}"'''.format(path)  # needs extra quotes to work as command line argument
        cmd = "C:\\s\\ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 %s"\
              % path
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

            cmd = "C:\\s\\ffmpeg.exe -ss %f -i %s -f image2pipe -vframes 1 -s 320x240 -"\
                  % (timepoint, '''"{}"'''.format(self.path))
            pipe = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, bufsize=10 ** 8)
            # a = pipe.communicate()
            # return a
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

    def get_time_points(self, timepoint=None, coarse=False, index=4):

        """returns 9 time points within self.duration, evenly spread with no other arguments or centred around time"""

        if timepoint:
            if index == 4:
                if coarse:
                    increment = self.increment * 4
                else:
                    increment = self.increment / 6.0
            else:
                increment = self.increment
                # don't change the increment if an index other than 4 is selected, this "re-centres" the seeking
            a = timepoint - (4 * increment)
            if a < 0:
                a = 0.1

            self.increment = increment  # remembered between calls for finer thumbs moved from 150

        else:
            a = 0.1
            increment = self.increment

        times = []

        while len(times) < 9:
            times.append(a)
            a += increment

            if a > self.duration:
                print("time beyond video end, truncating")
                a -= increment

        return times

    @staticmethod
    def get_video_res(fullpath):

        cmd = '''C:\\s\\ffprobe -v error -select_streams v:0 -show_entries stream=height,width -of csv=s=x:p=0 "%s"'''\
              % fullpath
        pipe = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, bufsize=10 ** 8)
        info2, error = pipe.communicate()
        info = info2.decode("utf-8")
        return info.rstrip("\r\n")
