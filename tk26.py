from tkinter import *
from PIL import Image, ImageTk, UnidentifiedImageError
from io import BytesIO
import threading
import os
import time
from collections import deque
from tkinter import simpledialog, font, filedialog
from dbman_v4 import DBManager
from videoobject import VideoObject, BadVideoException
from settings import SETTINGS, save_settings  # a dict containing values stored in the json file

"""The main program file, will create a database if necessary on first-time setup when none exists.
Specify settings in settings.json
Note this is designed to work with Windows type paths"""

TOP_LEVEL = SETTINGS["TOP_LEVEL"]
SQLPATH = SETTINGS["SQLPATH"]
# the number of rows and columns (x, y) for the tiles in the query window results pane
QUERY_X = SETTINGS["QUERY_X"]
QUERY_Y = SETTINGS["QUERY_Y"]


class ThumbGenerator:

    def __init__(self, list_of_paths):

        self.path_gen = None  # a generator object
        self.updater_running = False  # stop more than one updater thread
        self.deque = deque()
        self.update_path(list_of_paths)

    def update_path(self, list_of_paths):

        self.path_gen = iter(list_of_paths)
        self.deque.clear()
        self.update_queues()

    def get_next(self):

        """returns the next VideoObject"""

        if len(self.deque) > 0:
            obj = self.deque.pop()
        elif self.updater_running:
            print("Waiting for something to pop from the deque", end="")
            while len(self.deque) < 1:
                time.sleep(1)
                print(".", end="")
            obj = self.deque.pop()
            print()
        else:
            print("all files visited")
            return -1
        self.update_queues()

        return obj

    def update_queues(self):

        """checks if the updater thread is running, if not, starts it"""

        if not self.updater_running:
            th = threading.Thread(target=self.threaded_queue_updater)
            th.setDaemon(True)
            th.start()
        else:
            print("tried to start updater when updater is already running")

    def threaded_queue_updater(self):

        """gets a path from self.pathgen and runs the ffmpeg stuff to get the gif images,
        appendlefts a new VideoObject to the self.deque then returns None"""

        self.updater_running = True
        while len(self.deque) < 15:
            try:
                path = self.path_gen.__next__()
            except StopIteration:
                print("all files visited")
                self.updater_running = False
                return
            try:
                print("getting a videoobject for {}".format(path))
                # TODO: cope with unprintable chrs
            except UnicodeEncodeError:
                print("getting a videoobject for unprintable filename")
            try:
                obj = VideoObject(path)
            except BadVideoException:
                obj = path  # the video is broken, just put the path on the deque so that when the
                # main window pops it it knows it's broken and can remove the video from the db

            self.deque.appendleft(obj)
        self.updater_running = False
        return


class PicsWindow(Toplevel):

    """Common base class for ImageWindow and QueryWindow"""

    def __init__(self, parent, x=3, y=3, ph=None):

        """A grid of x by y image panels, packs itself to the right of the parent container"""

        super().__init__(parent)
        self.filename_font = font.Font(family="Helvetica", size="12")
        self.placeholder_image = ph
        self.parent = parent
        self.title("Results")  # this window title is changed by e.g. right clicking on query results

        self.path = None
        self.piclist = []  # to save reference to photoimages
        self.picture_panels = []  # reference to the labels showing the images
        self.time_labels = []  # timestamps to be displayed under thumbnails
        self.video_object = None  # reference to the video object currently displayed
        # self.file_name_display = Label(self, text="Results", bg="light grey", font=self.filename_font)
        # default text is "results" but always overwritten if it is a VideoObject
        # self.file_name_display.pack(side=TOP)

        self.picpanels_setup(x, y)
        self.save_pic = None  # to be queried by parent frame during save process

        self.index_from = 0  # used in update_images, not relevant for VideoObject use but useful for ResultsObjects

        self.geometry(SETTINGS["GEOMETRY_IMAGEWINDOW"])

    def on_left_click(self, e):

        pass  # overload in inheriting class

    def on_left_double_click(self, e):

        pass  # overload in inheriting class

    def on_right_click(self, e):

        pass  # overload in inheriting class

    def add_timestamp_labels(self, x):

        pass  # these are only used by ImageWindow but the method needs to be called during the loop that
        # fills the window with picture panels. ImageWindow overloads this method with its own that makes the labels.

    def select_image(self, x):

        pass  # for selecting an image by numpad keypress instead of mouse

    def picpanels_setup(self, x, y):

        """creates the picture panels and appends them to self.picture_panels. Binds commands to the label widgets"""

        pic = self.placeholder_image
        self.piclist.append(pic)

        if x == y == 3:  # set up the prescribed size for the tagging interface, in this case the window is const. size
            img_height = int(720 / x)
            img_width = int(1000 / y)
        else:  # user-defined results grid size, in this case the window changes size to accommodate the thumbnails
            img_height = 130
            img_width = 170

        # these numbers make a panel slightly bigger than a 320x240 video thumbnail to leave a border
        # panel size has to be manually specified because the placeholder and arrow images are smaller than a
        # thumbnail, so packing won't give a nice grid due to non-uniform image size, so we compute the geometry here

        counter = 0

        for i in range(0, y):  # for each row

            container = Frame(self)  # make a row frame that contains the thumbnail tiles

            for j in range(0, x):  # for each column/number of tiles in the horizontal direction
                picpanel = Label(container, height=img_height, width=img_width, image=pic, bg="light grey")
                #picpanel = Label(container, image=pic, bg="light grey")
                picpanel.number = counter
                self.picture_panels.append(picpanel)
                picpanel.pack(side=LEFT, fill=BOTH, expand=YES)
                picpanel.bind("<Button-1>", self.on_left_click)
                picpanel.bind("<Double-Button-1>", self.on_left_double_click)
                picpanel.bind("<Button-3>", self.on_right_click)
                counter += 1

            container.pack(side=TOP, fill=BOTH, expand=YES)
            # make a row of thumbnails, and pack it against the top of the frame
            self.add_timestamp_labels(x)  # this is just "pass" for a QueryWindow

    def set_videoobject(self, obj):

        self.index_from = 0
        self.video_object = obj
        self.update_images()

        if type(obj) == VideoObject:  # resultsobjects don't have filenames
            filename = obj.filename
            self.title(filename)
        else:
            self.title("Results")

    def update_images(self):

        """Gets images from self.videoobject, to be called after the video object updates itself"""

        index = self.index_from
        self.piclist = []  # clear to prevent storing old images forever

        for i in self.video_object.images:
            if i == self.placeholder_image:
                logo = i  # otherwise it will try to make a PhotoImage but placeholder is already a PhotoImage
            else:
                logo = ImageTk.PhotoImage(i)
            self.piclist.append(logo)

        for i in self.picture_panels:
            if index < len(self.piclist):  # to cope with being passed a small query
                i.configure(image=self.piclist[index], bg="light grey")
            else:
                i.configure(image=self.placeholder_image, bg="light grey")
            index += 1


class ImageWindow(PicsWindow):

    def add_timestamp_labels(self, x):

        timestamp_container = Frame(self)
        timestamp_container.pack(side=TOP, fill=BOTH, expand=YES)
        for j in range(0, x):
            timelabel = Label(timestamp_container, text="00:00:00")
            timelabel.pack(side=LEFT, expand=YES)
            self.time_labels.append(timelabel)

    def update_images(self):

        super().update_images()
        self.update_time_labels()  # only this interface needs time labels for the images
        self.save_pic = self.video_object.images[4]
        # random representative middle thumbnail if user doesn't select one at all

    def update_time_labels(self):

        timestamps = [VideoObject.timeconvert(x) for x in self.video_object.time_points]
        # a staticmethod of VideoObject

        cnt = 0
        for i in self.time_labels:
            i.configure(text="%s:%s" % (timestamps[cnt]))
            cnt += 1

    def on_right_click(self, e):

        self.video_object.refine()
        self.update_images()

    def on_left_double_click(self, event):

        os.startfile(self.video_object.path)

    def on_left_click(self, event):

        widget = event.widget
        index = widget.number
        self.set_save_pic(index)

    def select_image(self, event):

        """select an image in the grid on the basis of a numpad keypress. Note that the number
        has to be translated because the position of the image corresponds to the POSITION of the key,
        not the numerical value"""

        dc = {7:0, 8:1, 9:2, 4:3, 5:4, 6:5, 1:6, 2:7, 3:8}
        # translate to the right position and subtract 1 because we are indexing from 0
        num = int(event.char)  # convert the keypress to its int value
        self.set_save_pic(dc[num])  # look up the index from the key that was actually pressed

    def set_save_pic(self, index):

        """Index is 0-8 corresponding to the positions on the 3x3 thumbnail grid"""
        for i in self.picture_panels:
            i.configure(bg="light grey")  # reset everything rather than having to hold a ref to last

        self.save_pic = self.video_object.images[index]
        self.picture_panels[index].configure(bg="red")


class QueryWindow(PicsWindow):

    def __init__(self, parent, x, y, mainwindow_ref, ph):

        self.right_arrow_icon = mainwindow_ref.right_arrow_icon
        self.left_arrow_icon = mainwindow_ref.left_arrow_icon
        self.mainwindow_ref = mainwindow_ref
        # extra code to get the icons for fd/back arrow and put them in the picture panels
        super().__init__(parent, x, y, ph=ph)

    def on_left_click(self, event):

        """uses os.startfile on releveant path from selected thumbnail"""

        widget = event.widget
        index = widget.number
        index += self.index_from  # offset used if we are on screen 2,3... of results
        if not index > len(self.video_object.paths) - 1:
            path = self.video_object.paths[index]
            os.startfile(path)
            self.mainwindow_ref.db_manager.increment_play_count(path)
            self.mainwindow_ref.history_window.add(self.piclist[index], path)
        else:
            print("index beyond video list")

    def on_right_click(self, event):

        """overloaded to query tags from the parent's database object"""
        # print(len(self.picture_panels))

        cnt = 0
        for i in self.picture_panels:
            if cnt < len(self.piclist) - self.index_from:
                i.configure(bg="light grey")
                # reset colours so that old green highlights don't linger, but don't go beyond len of piclist
                cnt += 1

        widget = event.widget
        index = widget.number + self.index_from
        if not index > len(self.video_object.paths) - 1:
            widget.configure(bg="light green")
            video_path = self.video_object.paths[index]
            video_key = video_path  # replace above, use full path not just filename
            self.mainwindow_ref.update_tags(video_key)
            # self.file_name_display.configure(text=video_path)
            self.title(video_path)
        else:
            print("index beyond video list")

    def picpanels_setup(self, x, y):

        super().picpanels_setup(x, y)

        # re-bind commands for first and last picture panels for use as forward/back button

        null_method = lambda: None

        self.picture_panels[0].bind("<Button-1>", self.prev_image_set)
        self.picture_panels[0].bind("<Double-Button-1>", self.prev_image_set)
        self.picture_panels[0].bind("<Button-2>", null_method)
        self.picture_panels[0].bind("<Button-3>", null_method)
        self.picture_panels[0].configure(image=self.left_arrow_icon, bg="light grey")

        self.picture_panels[-1].bind("<Button-1>", self.next_image_set)
        self.picture_panels[-1].bind("<Double-Button-1>", self.next_image_set)
        self.picture_panels[-1].bind("<Button-2>", null_method)
        self.picture_panels[-1].bind("<Button-3>", null_method)
        self.picture_panels[-1].configure(image=self.right_arrow_icon, bg="light grey")

        self.picture_panels.pop()
        self.picture_panels.pop(0)  # remove first and last panels to reserve for use as fwd/back buttons

        for panel in self.picture_panels:
            panel.number -= 1  # compensate for reserving first and last

    def next_image_set(self, event):

        if self.index_from + len(self.picture_panels) < len(self.video_object.images):
            self.index_from += len(self.picture_panels)
            # might have gone forward then back, so can go forward again without
            # asking the generator for a new batch of results
        else:
            try:
                self.video_object.add_batch()
                self.index_from += len(self.picture_panels)
            except StopIteration:
                print("results generator exhausted")

        self.update_images()
        self.mainwindow_ref.deselect_update()
        # self.file_name_display.configure(text="Results")  # clear selection
        self.title("Results")

    def prev_image_set(self, event):

        if not self.index_from == 0:
            self.index_from -= len(self.picture_panels)
            self.update_images()
        else:
            print("can't go back any further")

        self.mainwindow_ref.deselect_update()
        # self.file_name_display.configure(text="Results")  # clear selection
        self.title("Results")


class HistoryWindow(PicsWindow):

    def __init__(self, parent, ph):

        super().__init__(parent, x=6, y=9, ph=ph)
        self.current = 0  # the index of where to put the next thumbnail
        self.paths = [None] * len(self.picture_panels)
        self.geometry(SETTINGS["GEOMETRY_HISTORY_WINDOW"])
        self.images = [None] * len(self.picture_panels)
        # need to hold our own reference to images or they'll be garbage collected
        self.title("History")

    def add(self, thumbnail, fullpath):

        """Add a video to the history and display it"""

        pan = self.picture_panels[self.current]
        self.images[self.current] = thumbnail
        pan.configure(image=self.images[self.current])
        self.paths[self.current] = fullpath
        self.current += 1
        if self.current >= len(self.picture_panels):
            self.current = 0

    def on_left_click(self, e):

        os.startfile(self.paths[e.widget.number])
        # this doesn't update the "times played" count but that's not really that useful anyway


class ResultsObject:

    """behaves like a VideoObject, can be passed to the querywindow for displaying the results of a query"""

    def __init__(self, gen, batch_size=32, placeholder=None):

        """gen is a generator yielding tuples of thumbnail, fullpath
        this class gets the placeholder image passed to it by the main window
        which has access to the database and can load the placeholder image"""

        self.generator = gen
        self.batch_size = batch_size  # number of results displayed at once in results panel
        self.images = []
        self.paths = []
        self.placeholder_image = placeholder
        try:
            self.add_batch()  # read in the first lot of results from the generator
        except StopIteration:
            # no results were found
            pass  # the placeholder images will remain

    def add_batch(self):

        """reads a batch of new results and adds them to the internal list"""

        try:
            new_batch = self.generator.__next__()
        except StopIteration:
            raise StopIteration
            # it's not really a generator but this tells the QueryWindow there are no more

        new_images = []
        for qq in new_batch:

            pth = qq[1]  # in case need to print path name for image getting error

            try:
                im = Image.open(BytesIO(qq[0])).resize((160, 120))
            except UnidentifiedImageError:
                im = self.placeholder_image
                print(f"Error getting image for {pth}")
            new_images.append(im)

        new_paths = [x[1] for x in new_batch]
        self.images.extend(new_images)
        self.paths.extend(new_paths)


class MainWindow:
    def __init__(self, parent):

        self.button_font = font.Font(family="Helvetica", size="12")
        self.parent = parent  # ref held for starting query mode or making new windows outside of init

        self.parent.geometry(SETTINGS["GEOMETRY_MAIN"])
        self.db_manager = DBManager(SQLPATH)
        self.tag_group_1, self.tag_group_2, self.extensions = self.db_manager.get_tag_settings()

        la, ra, ph = self.db_manager.get_icons()  # function returns images in predefined order

        self.placeholder_image = ImageTk.PhotoImage(Image.open(BytesIO(ph)).resize((80, 80)))
        self.left_arrow_icon = ImageTk.PhotoImage(Image.open(BytesIO(la)).resize((80, 80)))
        self.right_arrow_icon = ImageTk.PhotoImage(Image.open(BytesIO(ra)).resize((80, 80)))

        self.done_objects = []  # session-specific list for history seeking purposes, max. length 10 items
        self.saved_objects = []  # current videoobject is saved to return to later if seeking
        self.key_to_update = None  # for above
        self.last_tags = []  # if the next video has the same tags saves having to re-enter all of them
        self.query_mode = True  # start in query mode
        self.tag_mode = False
        self.found_video = ""  # the name of the video being played in some media player for scan mode
        self.thumbgenerator = None  # this is instantiated in another function
        self.scan_task_id = None  # reference to the scanning task in tkinter event loop for cancellation

        self.xtiles = QUERY_X
        self.ytiles = QUERY_Y  # store geometry in this object in case the user updates it via the interface
        # TODO: interface menu to change the size of the query window?
        self.tile_count = self.xtiles * self.ytiles - 2  # grid size, minus 2 for the forward and back arrows

        self.left_container = Frame(parent)
        self.right_container = Frame(parent)
        self.picpanel = ImageWindow(parent, ph=self.placeholder_image)

        self.query_button = Button(self.left_container)
        self.query_button.configure(text="Query mode", command=self.start_query_mode)
        self.query_button.pack(fill=BOTH, expand=YES)

        self.tagging_button = Button(self.left_container)
        self.tagging_button.configure(text="Tagging mode", command=self.start_tag_mode)
        self.tagging_button.pack(fill=BOTH, expand=YES)

        self.r_tagging_button = Button(self.left_container)
        self.r_tagging_button.configure(text="Tag randomly", command=lambda: self.start_tag_mode(True))
        self.r_tagging_button.pack(fill=BOTH, expand=YES)

        self.select_dir_button = Button(self.left_container)
        self.select_dir_button.configure(text="Directory...", command=self.select_directory)
        self.select_dir_button.pack(fill=BOTH, expand=YES)

        self.scan_changes_button = Button(self.left_container)
        self.scan_changes_button.configure(text="Scan for new files", command=self.scan_for_new_files)
        self.scan_changes_button.pack(fill=BOTH, expand=YES)

        self.free_space_button = Button(self.left_container)
        self.free_space_button.configure(text="Free up library space", command=self.free_space)
        self.free_space_button.pack(fill=BOTH, expand=YES)

        self.category_container = Frame(self.right_container, borderwidth=5, relief=RIDGE)
        self.extras_container = Frame(self.right_container, borderwidth=5, relief=RIDGE)
        self.text_container = Frame(self.right_container, borderwidth=5, relief=RIDGE)
        self.arrows_container = Frame(self.left_container, borderwidth=5, relief=RIDGE)

        self.category_container.name = "tag_group_1"
        self.extras_container.name = "tag_group_2"

        self.left_container.pack(side=LEFT, padx=40)
        self.right_container.pack(side=LEFT)

        self.arrows_container.pack(pady=20, fill=BOTH, expand=YES)

        next_button = Button(self.arrows_container)
        next_button.configure(text=">", width=10, height=2, font=self.button_font, command=self.next_entry, pady=20)
        next_button.pack(side=RIGHT, expand=YES, fill=BOTH)

        prev_button = Button(self.arrows_container)
        prev_button.configure(text="<", width=10, height=2, font=self.button_font, command=self.previous_entry, pady=20)
        prev_button.pack(side=LEFT, expand=YES, fill=BOTH)

        self.controls_container = Frame(self.left_container, borderwidth=5, relief=RIDGE)
        self.controls_container.pack(fill=BOTH, expand=YES)

        self.clear_tags_button = Button(self.controls_container)
        self.clear_tags_button.configure(font=self.button_font, text="Clear", command=self.reset_buttons)
        self.clear_tags_button.pack(side=LEFT)

        self.commit_changes_button = Button(self.controls_container)
        self.commit_changes_button.configure(font=self.button_font, text="Commit", command=self.commit_change)
        self.commit_changes_button.pack(side=LEFT)

        self.repeat_tags_button = Button(self.controls_container)
        self.repeat_tags_button.configure(font=self.button_font, text="Clone prev.", command=self.repeat_tags)
        self.repeat_tags_button.pack(side=LEFT)

        self.rquery_button = Button(self.controls_container)
        self.rquery_button.configure(font=self.button_font, text="Results", command=self.get_query_results)
        self.rquery_button.pack(side=LEFT)

        self.newquery_button = Button(self.controls_container)
        self.newquery_button.configure(font=self.button_font, text="New results", command=self.new_query_results)
        self.newquery_button.pack(side=LEFT)

        for k in (self.category_container, self.extras_container):
            button = Button(k)
            button.configure(text="add", command=lambda container=k: self.add_button(container))
            button.grid()
            button.value = 0  # so that it doesn't crash the button value reading method
            k.current_row = 0
            k.current_column = 0

        self.text_search_button = Button(self.text_container)
        self.text_search_button.configure(text="Search by title", font=self.button_font, command=self.search_by_title)
        self.text_search = Entry(self.text_container, width=20)
        self.text_search.pack(side=LEFT, padx=20)
        self.text_search_button.pack(side=LEFT, padx=20)

        self.extras_container.pack(fill=BOTH, expand=YES)
        self.category_container.pack(fill=BOTH, expand=YES)
        self.text_container.pack()

        for entry in sorted(self.tag_group_1):
            self.add_button(container=self.category_container, name=entry)
        self.extras_container.pack()
        for entry in sorted(self.tag_group_2):
            self.add_button(container=self.extras_container, name=entry)
        self.arrows_container.pack()

        self.setup_num_bindings()  # bind numeric keypad to thumbnail 1-9 for selection while tagging

        self.start_query_mode()

    def setup_num_bindings(self):

        for x in range(1,10):  # keys 1...9 inclusive
            self.parent.bind(str(x), lambda e: self.picpanel.select_image(e))

    def add_button(self, container, name=None):  # name arg for pre-made names read in from saved settings

        container.current_row += 1
        if container.current_row > 5:
            container.current_row = 0
            container.current_column += 1

        row = container.current_row
        column = container.current_column

        if not name:
            name = simpledialog.askstring("", "Enter tag name")

            if name is None:
                return  # user cancelled new tag creation
            if container.name == "tag_group_1":
                self.tag_group_1.append(name)
            elif container.name == "tag_group_2":
                self.tag_group_2.append(name)
            self.db_manager.add_tag(container.name, name)

        button = Button(container)
        button.value = 0
        button.configure(text=name, font=self.button_font,
                         command=lambda b=button: MainWindow.selection_button_cmd(b))
        button.grid(row=row, column=column, sticky=E + W)

    @staticmethod
    def selection_button_cmd(widget):

        colourkey = ["gray92", "green", "pink"]

        widget.value += 1
        if widget.value > 2:
            widget.value = 0
        widget.configure(background=colourkey[widget.value])

    def save_entry(self):

        gif_image = self.picpanel.save_pic
        full_path = self.picpanel.video_object.path
        tag_group_1, tag_group_2 = self.get_button_values()
        self.last_tags = tag_group_1 + tag_group_2
        # store last if next video has identical tags and the user wants to clone them

        self.db_manager.write_entry(full_path, tag_group_1, tag_group_2)
        image_bytes = BytesIO()
        gif_image.save(image_bytes, "GIF")
        image_bytes.seek(0)
        self.db_manager.assign_thumbnail(full_path, image_bytes.read())
        try:
            print("Wrote info for {}".format(full_path))
        except UnicodeEncodeError:
            print("Wrote info for unprintable filename")

    def skip_entry(self):

        try:
            full_path = self.picpanel.video_object.path
        except AttributeError:
            full_path = None
        self.db_manager.skip_entry(full_path)

    def repeat_tags(self):

        for i in (self.category_container, self.extras_container):

            children = i.winfo_children()
            for j in children:
                if type(j) == Button:
                    if j["text"] in self.last_tags:
                        j.value = 1
                        j.configure(background="green")

    def next_entry(self, override=None):  # override added new when getting currently viewed video

        if not self.get_button_values() == [[], []]:
            self.save_entry()
        else:  # no tags were assigned, the user skipped the video & it probably isn't interesting
            self.skip_entry()

        self.done_objects.append(self.picpanel.video_object)
        # object held for being able to go back and re-create VideoObject
        if len(self.done_objects) > 50:
            self.done_objects.pop(0)  # but also stop the list getting too long

        self.reset_buttons()

        if not self.saved_objects:  # the list is empty, not seeking back
            if override:
                obj = override
            else:
                obj = self.thumbgenerator.get_next()
                while type(obj) is str:  # take care of as many broken videos as necessary
                    self.db_manager.broken_file(obj)
                    obj = self.thumbgenerator.get_next()

        else:
            obj = self.saved_objects.pop()
            try:
                self.update_tags(obj.path)  # re-load and display the object's tags
            except KeyError:
                pass  # object had been viewed but not tagged yet
        if not (obj is None or obj == -1):

            self.picpanel.set_videoobject(obj)

        else:
            print("got nonetype from thumb generator")

    def previous_entry(self):

        if not self.done_objects == []:
            self.saved_objects.append(self.picpanel.video_object)
            # save the currently viewed object to return to later
            obj = self.done_objects.pop()
        else:
            print("no previous entry stored")
            return

        self.picpanel.set_videoobject(obj)

        try:
            self.update_tags(obj.path)
        except KeyError:  # file was skipped and not tagged at all
            self.reset_buttons()

    def get_button_values(self):

        ls = []

        for i in (self.category_container, self.extras_container):
            taglist = []
            children = i.winfo_children()
            for j in children:
                if type(j) == Button:
                    if not j.value == 0:  # can be 1 (tag once) or 2 (tag and conserve tag for next entry)
                        taglist.append(j["text"])

            ls.append(taglist)
        return ls

    def reset_buttons(self):

        for i in (self.category_container, self.extras_container):
            children = i.winfo_children()
            for j in children:
                if type(j) == Button:
                    if j.value == 1:  # reset values stored in button if it has been clicked but not if clicked twice
                        j.value = 0
                        j.configure(background="gray92")

    def start_query_mode(self):

        print("Query mode started")
        self.reset_buttons()
        self.query_mode = True
        self.tag_mode = False
        self.picpanel.destroy()
        self.picpanel = QueryWindow(parent=self.parent, x=self.xtiles, y=self.ytiles,
                                    mainwindow_ref=self, ph=self.placeholder_image)
        self.history_window = HistoryWindow(parent=self.parent, ph=self.placeholder_image)

    def start_tag_mode(self, randomly=False):

        print("Tag mode started")
        self.reset_buttons()
        self.query_mode = False
        self.tag_mode = True
        self.picpanel.destroy()
        self.picpanel = ImageWindow(self.parent)

        if not randomly:
            apath = filedialog.askdirectory()
            # apath = apath.split("/")[1]
            apath = os.path.split(apath)[1]
            # db manager's path generator expects just the name of the directory for an SQL query
            list_of_paths = self.db_manager.path_generator(apath, random=False)
        else:
            list_of_paths = self.db_manager.path_generator(None, random=True)

        self.thumbgenerator = ThumbGenerator(list_of_paths)

        no_dir = False
        video_object = None
        while video_object is None:
            video_object = self.thumbgenerator.get_next()
            # todo: this code is duplicated in the next_entry function
            while type(video_object) is str:  # take care of as many broken videos as necessary
                self.db_manager.broken_file(video_object)
                video_object = self.thumbgenerator.get_next()

            if video_object == -1:
                no_dir = True
                break

        if not no_dir:
            self.picpanel.set_videoobject(video_object)

    def update_tags(self, key):

        self.reset_buttons()
        result = self.db_manager.get_entry(key)
        self.key_to_update = key
        info_list = result.tag_group_1 + result.tag_group_2

        for i in (self.category_container, self.extras_container):

            children = i.winfo_children()
            for j in children:
                if type(j) == Button:
                    if j["text"] in info_list:
                        j.value = 1
                        j.configure(background="green")

    def commit_change(self):

        if not self.query_mode:
            print("not in query mode or scan mode")
            return
        tag_group_1, tag_group_2 = self.get_button_values()

        if not self.key_to_update:  # clicked "commit" without having a video selected
            return
        if not self.db_manager.check_has_thumbnail(self.key_to_update):
            self.save_entry()  # if no thumbnail, it hasn't been tagged before and needs new entry
        else:
            self.db_manager.write_entry(self.key_to_update, [], [])  # clear previous tag values
            self.db_manager.write_entry(self.key_to_update, tag_group_1, tag_group_2)

        self.reset_buttons()

    def deselect_update(self):  # clears the queried tags if scrolling thru multiple pages after updating some tags

        self.reset_buttons()
        self.key_to_update = None

    def new_query_results(self):

        # TODO: refactor, copy-pasted from below
        if not self.query_mode:
            return

        queryls = self.get_button_values()
        results = self.db_manager.newest_matches(*queryls, batch_size=self.tile_count)

        obj = ResultsObject(results, placeholder=self.placeholder_image)
        self.picpanel.set_videoobject(obj)


    def get_query_results(self):

        if not self.query_mode:
            return

        queryls = self.get_button_values()
        results = self.db_manager.get_matches(*queryls, batch_size=self.tile_count)

        obj = ResultsObject(results, placeholder=self.placeholder_image)
        self.picpanel.set_videoobject(obj)

    def search_by_title(self):

        if not self.query_mode:
            return

        qry = self.text_search.get()
        results = self.db_manager.text_search(qry, batch_size=self.tile_count)

        obj = ResultsObject(results, placeholder=self.placeholder_image)
        self.picpanel.set_videoobject(obj)  # TODO: bit of code duplication with above

    def on_quit(self):

        SETTINGS["GEOMETRY_MAIN"] = self.parent.geometry()
        SETTINGS["GEOMETRY_IMAGEWINDOW"] = self.picpanel.geometry()
        SETTINGS["GEOMETRY_HISTORY_WINDOW"] = self.history_window.geometry()
        save_settings()  # remember window geometries

        self.db_manager.commit_changes()
        self.parent.destroy()

    def scan_for_new_files(self):

        """Asks the dbmanager to walk the directory and add new files it finds"""

        self.db_manager.scan_for_new_files(TOP_LEVEL)

    def free_space(self):

        """Free up space in the main library by moving files to a trash directory defined in settings.json"""

        amt = simpledialog.askstring("", "Space to free up (GB)")
        if not amt:
            return  # user cancelled
        try:
            amount = float(amt)
        except ValueError:
            print(f"Problem converting number {amt} to float")
            return
        amount = amount * (1024 * 1024 * 1024)  # gigs to bytes
        self.db_manager.free_up_space(amount)

    def select_directory(self):

        if self.tag_mode:

            path = filedialog.askdirectory()
            # print("path is")
            # print(path)
            path = path.replace("/", "\\")  # convert to windows-type path
            self.done_objects = []
            self.saved_objects = []
            self.thumbgenerator.update_path(path)
            self.picpanel.set_videoobject(self.thumbgenerator.get_next())

        elif self.query_mode:

            path = filedialog.askdirectory()
            if not path:
                self.db_manager.remove_directory_filter()
            else:
                # print("Filtering results to {}".format(path))
                bits = path.split("/")
                folder = bits[1]
                self.db_manager.set_directory_filter(folder)


root = Tk()
myapp = MainWindow(root)
root.protocol("WM_DELETE_WINDOW", myapp.on_quit)  # bind function only to commit db changes on quit
root.title("video tagger")
root.mainloop()
