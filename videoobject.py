from tkinter import *
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import subprocess as sp
from settings import SETTINGS
from random import randint

FFMPEG = SETTINGS["FFMPEG_PATH"]
FFPROBE = SETTINGS["FFPROBE_PATH"]

class BadVideoException(Exception):

    pass


class VideoObject:

    """Container for information about a video file. Generates thumbnails with ffmpeg and stores them, also
    gets general info like duration, resolution, etc, to be made available to the main program."""

    def __init__(self, full_path, thumbnails=9):

        """By default get 9 images for the GUI, but can ask for more when e.g. making contact sheets"""

        self.path = full_path
        filename = os.path.split(self.path)[1]
        self.filename = filename.rstrip("\"")  # filename final quote mark stripped off
        self.duration, self.increment = self.get_initial_info(self.path, thumbnails)
        if self.duration is not None:
            # if it's none then this video has broken ffmpeg
            self.time_points = self.get_time_points(thumbnails)
            try:
                self.images = self.get_thumbnails(self.time_points)
            except BadVideoException:
                raise BadVideoException(f"ffmpeg could not read the file at {full_path}")

    def refine(self):

        """apply a small delta to the thumbnail time points to get different images"""

        tp = self.time_points
        tp2 = [randint(-5, 5) + x for x in tp]
        # check to make sure the random addition hasn't put the time outside of the video length
        if tp2[0] < 0:
            tp2[0] = 0.1
        if tp2[-1] > self.duration:
            tp2[-1] = self.duration - 1
        self.time_points = tp2
        self.images = self.get_thumbnails(self.time_points)

    @staticmethod
    def get_initial_info(path, no_thumbnails):

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

        increment = duration / float(no_thumbnails + 1)

        return duration, increment

    def get_thumbnails(self, times):

        """returns a list of gif images at the times given"""

        def get_image(timepoint):

            cmd = f'''{FFMPEG} -ss {timepoint} -i "{self.path}" -f image2pipe -vframes 1 -s 320x240 -'''
            pipe = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, bufsize=10 ** 8)

            return pipe

        images_to_return = []
        pipes = []

        for i in times:
            # it seems inefficient to load up ffmpeg multiple times but this allows direct seeking
            # to the desired time point. By using the fps filter with a fractional number, the
            # images can be got with one call to ffmpeg but it's much slower and CPU intensive
            # as the entire video must be decoded rather than seeking by keyframe.
            data = get_image(i)
            pipes.append(data)

        for p in pipes:
            try:
                imagedata2 = p.communicate(timeout=15)
            except sp.TimeoutExpired:
                print("ffmpeg timed out getting thumbnails")
                p.kill()
                return []
            imagedata = imagedata2[0]
            flo = BytesIO(imagedata)
            try:
                image = Image.open(flo)
            except:
                # print("error opening image")
                # print(imagedata2[1])  # print ffmpeg's stderr to the console
                raise BadVideoException

            images_to_return.append(image)

        return images_to_return

    def get_time_points(self, number):

        """returns 9 time points within self.duration, evenly spread with no other arguments or centred around time"""

        a = 3.0
        times = []

        while len(times) < number:
            times.append(a)
            a += self.increment

            if a > self.duration:
                print("time beyond video end, truncating")
                a -= self.increment

        return times

    @staticmethod
    def get_video_res(fullpath):

        cmd = f'''{FFPROBE} -v error -select_streams v:0 -show_entries stream=height,width -of csv=s=x:p=0 "{fullpath}"'''
        pipe = sp.Popen(cmd, stdout=sp.PIPE, stderr=sp.PIPE, bufsize=10 ** 8)
        info2, error = pipe.communicate()
        info = info2.decode("utf-8")
        return info.rstrip("\r\n")

    def write_contact_sheet(self, directory):

        """writes a 3x3 thumbnail sheet using the generated images to the given directory path"""

        a, b = divmod(len(self.images), 3)
        height_needed = a * 250  # 240 px thumbnail height with 10 px gap
        if not b == 0:
            height_needed += 250  # extra row
        height_needed += 150  # for title info
        container = Image.new("RGB", (1000, height_needed))
        ctx = ImageDraw.Draw(container)
        font = ImageFont.truetype("arial.ttf", 20)
        font2 = ImageFont.truetype("arial.ttf", 16)

        it = iter(self.images)
        it2 = iter(["{}:{}".format(*self.timeconvert(x)) for x in self.time_points])
        y = 100  # vertical coordinate to start drawing
        while y < height_needed - 250:
            for x in (10, 340, 670):
                try:
                    container.paste(next(it), (x,y))
                    ctx.rectangle((x, y, x + 45, y + 20), fill=(0, 0, 0))  # to write the timestamp text
                    ctx.text((x+1, y+1), next(it2), font=font2)
                except StopIteration:
                    break  # in case the number of thumbnails gives an incomplete row
            y += 250

        ctx.text((10, 10), self.filename, font=font)
        extra_info = f'''{self.get_video_res(self.path)},  {"{}:{}".format(*self.timeconvert(self.duration))}'''
        ctx.text((10, 50), extra_info, font=font)

        savepath = os.path.join(directory, self.filename) + ".jpg"
        container.save(savepath)

        return container

    @staticmethod
    def timeconvert(fl):

        """convert float to mm:ss"""

        m, s = divmod(round(fl), 60)
        m = str(m).zfill(2)
        s = str(s).zfill(2)
        return m, s



