import sqlite3
from collections import namedtuple
import os
from hashlib import md5
from videoobject import VideoObject
import time  # need for time of deletion in removed db
import json
from shutil import move, Error
from settings import SETTINGS, DELETION_WHITELIST
DUPES_FOLDER = SETTINGS["DUPES_FOLDER"]
TRASH_FOLDER = SETTINGS["TRASH_FOLDER"]

"""Module for interfacing with the sqlite database. This internally takes care of the conversion of tags to
bitmaps and back again, so the calling interface only sees lists of tags. Handles scanning for new files and
generating lists of videos yet to be tagged, etc."""

import datetime


def get_today_date():

    """for making the duplication report filename"""

    return datetime.date.today().isoformat()

def forty_days_ago():

    return int(time.time() - 3456000)


class DBManager:

    def __init__(self, db_path):

        """tag_group_1 and tag_group_2 are received in a canonical order for computing
        the bits"""

        if os.path.exists(db_path):
            self.db = sqlite3.connect(db_path)
        else:
            # first-time setup
            self.db = sqlite3.connect(db_path)
            setup_script = open("schema.sql", "r").read()
            self.db.executescript(setup_script)

        self.db_cursor = self.db.cursor()
        self.dbrow = self.setup_dbrow()  # this function returns a namedtuple
        self.tag_group_1 = []
        self.tag_group_2 = []
        self.tag_group_1_rev = {}
        self.tag_group_2_rev = {}  # {int value: "type"}
        self.tag_val_dict = {}  # {"type":int value}
        self.extensions = []
        self.values_setup()  # all the above are now read from DB file
        self.filter_directory = None  # if this is set, only return results from this top level direcotry

    def setup_dbrow(self):

        """Gets the column info from the videos table.
        Returns a namedtuple function based on the column names
        for converting database rows to namedtuples without
        having to know the column names beforehand in case of changes"""

        self.db_cursor.execute('''pragma table_info(videos)''')
        res = self.db_cursor.fetchall()
        colnames = []
        for tup in res:
            cid, cname, data_type, a, b, c = tup
            # scores are converted to lists of tags so these columns are renamed as the
            # main window does not directly understand the scores
            if cname == "score_1":
                cname = "tag_group_1"
            if cname == "score_2":
                cname = "tag_group_2"
            colnames.append(cname)
        print("found the following column names:")
        print(colnames)
        return namedtuple("dbrow", colnames + ["thumbnail"])
        # need to manually add thumbnail because it comes from a seperate table

    def values_setup(self):

        """Reads in the tag values from the database tables for tag_group_1 and tag_group_2
        set self.tag_group_1, self.tag_group_2 and self.extensions"""

        self.db_cursor.execute('''select * from tag_group_1''')
        for row in self.db_cursor.fetchall():
            tag, value = row
            self.tag_group_1.append(tag)
            self.tag_group_1_rev[value] = tag
            self.tag_val_dict[tag] = value

        self.db_cursor.execute('''select * from tag_group_2''')
        for row in self.db_cursor.fetchall():
            tag, value = row
            self.tag_group_2.append(tag)
            self.tag_group_2_rev[value] = tag
            self.tag_val_dict[tag] = value

        # self.db_cursor.execute('''select * from extensions''')
        # self.extensions = [x[0] for x in self.db_cursor.fetchall()]  # extensions are now stored in the json
        with open("settings.json", "r") as f:
            dat = json.load(f)
            self.extensions = dat["EXTENSIONS"]
            print("recognised extensions:", self.extensions)

    def get_tag_settings(self):

        """MainWindow needs this information to set up buttons and for the path generator"""

        return self.tag_group_1, self.tag_group_2, self.extensions

    def ints_to_tags(self, score_1, score_2):

        """takes ints for tag_group_1 and tag_group_2 and returns a list of tag strings"""

        tag_group_1 = []
        tag_group_2 = []
        for taglist, integer, adict in zip((tag_group_1, tag_group_2),
                                           (score_1, score_2),
                                           (self.tag_group_1_rev, self.tag_group_2_rev)):
            i = 0
            while i <= max(len(self.tag_group_1), len(self.tag_group_2)):  # binary up to highest needed
                toand = 2 ** i
                if integer is None:  # might be null value in db
                    integer = 0

                if toand & integer == toand:  # common bit
                    try:
                        taglist.append(adict[toand])
                    except KeyError:
                        print("key error for {}".format(toand))
                i += 1
        return tag_group_1, tag_group_2

    def tags_to_ints(self, tag_group_1, tag_group_2):

        """Takes a pair of lists for tag_group_1/tag_group_2 and returns the pair of ints
        by computing the score via the binary values of each tag stored in the tag value dict"""

        score_1 = 0
        score_2 = 0
        for tag in tag_group_1:
            score_1 += self.tag_val_dict[tag]
        for tag in tag_group_2:
            score_2 += self.tag_val_dict[tag]

        return score_1, score_2

    def add_tag(self, kind, name):

        """Add a new tag to the db from the interface. Type is tag_group_1 or tag_group_2.
        calculates the value and inserts into the tags table"""

        # can't use a placeholder for a table name so use string formatting:
        sqlstring1 = '''select max(value) from {}'''.format(kind)
        sqlstring2 = '''insert into {} (tag, value) values (?, ?)'''.format(kind)

        self.db_cursor.execute(sqlstring1)
        max_value = self.db_cursor.fetchone()[0]  # from tuple
        if max_value:
            new_value = max_value * 2
        else:
            new_value = 1  # NULL will be returned the first time the db is created, we are making
            # the first entry in the tag table here
        self.db_cursor.execute(sqlstring2, (name, new_value))
        print("Inserted {} into {} with value {}".format(name, kind, new_value))
        self.db.commit()
        self.values_setup()  # re-read the tag values to include the new one

    def write_entry(self, fullpath, tag_group_1, tag_group_2):

        """Write tags for entry identified by fullpath"""

        score_1, score_2 = self.tags_to_ints(tag_group_1, tag_group_2)
        timenow = int(time.time())
        self.db_cursor.execute('''update videos set score_1 = ?, 
                                score_2 = ? , 
                                skipped = 0,
                                tagged_when = ? 
                                where fullpath = ?''',
                               (score_1, score_2, timenow, fullpath))

        self.db.commit()

    def increment_play_count(self, fullpath):

        print(fullpath)
        self.db_cursor.execute('''update videos set times_viewed = times_viewed + 1
                                where fullpath = ?''', (fullpath,))
        self.db.commit()

    def skip_entry(self, fullpath):

        """Set the skipped flag so that the video is not re-visted during later tagging sessions. Skipped videos
        are never returned as search results even if the user searches on no tags."""

        self.db_cursor.execute('''update videos set skipped = 1 where fullpath = ?''', (fullpath,))
        self.db.commit()

    def assign_thumbnail(self, fullpath, gif):

        """Identifying an entry by fullpath, write a gif blob to the database"""

        self.db_cursor.execute('''update thumbnails set thumbnail = ? where fullpath = ?''',
                               (gif, fullpath))

    def commit_changes(self):

        """what it sez"""

        print("committing changes to database and closing connection")
        self.db.commit()
        self.db.close()

    def get_entry(self, fullpath):

        """gets the info for a video, finds the thumbnail from the thumbnails table and joins these results togeter,
        returns a namedtuple"""

        self.db_cursor.execute('''select * from videos where fullpath = ?''', (fullpath,))
        res = self.db_cursor.fetchone()
        self.db_cursor.execute('''select * from thumbnails where fullpath = ?''', (fullpath,))
        res2 = self.db_cursor.fetchone()

        return self.make_dbrow(res + (res2[0],))

    def filename_to_fullpath(self, filename):

        """Function for use with scan mode to find the full path"""

        self.db_cursor.execute('''select fullpath from videos where filename = ?''',
                               (filename,))

        results = [x for x in self.db_cursor.fetchall()]
        if len(results) > 1:
            print("NAME COLLISION for {}".format(filename))
        return results[0][0]  # a list of tuples containing one value

    def get_matches(self, tag_group_1, tag_group_2, batch_size=34):

        offset = 0
        gqscore, eqscore = self.tags_to_ints(tag_group_1, tag_group_2)

        self.db_cursor.executescript('''drop table if exists abcd;
                                        create table abcd (fp TEXT, tagged_when INTEGER)''')
        if self.filter_directory:
            self.db_cursor.execute('''insert into abcd (fp, tagged_when) 
                                            select fullpath, tagged_when from videos 
                                            where score_1 & ? = ? and
                                            score_2 & ? = ? and
                                            directory = ? order by random()''',
                                   (gqscore, gqscore, eqscore, eqscore, self.filter_directory))
        else:
            self.db_cursor.execute('''insert into abcd (fp, tagged_when)
                                select fullpath, tagged_when from videos 
                                where score_1 & ? = ? and
                                score_2 & ? = ? order by random()''',
                                   (gqscore, gqscore, eqscore, eqscore))

        # this sets up a temporary table from which we select chunks which are joined on
        # the thumbnails table, joining all results at once is too slow

        recent = forty_days_ago()  # always return some recently-tagged videos

        sc = '''drop view if exists pqrs;
                create temp view pqrs as 
                select * from abcd 
                where tagged_when <= {}
                or tagged_when is null 
                limit {} offset {};
                '''
        sc_new = '''drop view if exists tuvw;
                create temp view tuvw as 
                select * from abcd 
                where tagged_when > {} 
                limit {} offset {};
                '''

        selector = '''select thumbnail, fullpath from {view} 
                        inner join 
                        thumbnails on thumbnails.fullpath = {view}.fp'''

        new_qty = 4  # the amount of newly tagged videos to introduce to the results
        offset_new = new_qty
        # offset_old = batch_size - new_qty

        self.db_cursor.executescript(sc_new.format(recent, new_qty, offset))
        self.db_cursor.execute(selector.format(view="tuvw"))
        outb = self.db_cursor.fetchall()
        if len(outb) < new_qty:
            new_qty = len(outb)

        self.db_cursor.executescript(sc.format(recent, batch_size - new_qty, offset))
        self.db_cursor.execute(selector.format(view="pqrs"))
        outa = self.db_cursor.fetchall()

        out = outb + outa  # mostly any videos, but with guaranteed some recent ones
        while not out == []:
            print(f"{len(outb)}, {len(outa)}")
            print(new_qty)
            yield out
            offset += batch_size

            self.db_cursor.executescript(sc_new.format(recent, new_qty, offset_new))
            self.db_cursor.execute(selector.format(view="tuvw"))
            outb = self.db_cursor.fetchall()

            offset_new += new_qty

            if len(outb) < new_qty:
                new_qty = len(outb)  # run out of new stuff so return more old

            self.db_cursor.executescript(sc.format(recent, batch_size - new_qty, offset - new_qty))
            self.db_cursor.execute(selector.format(view="pqrs"))
            outa = self.db_cursor.fetchall()

            out = outb + outa

        return

    def make_dbrow(self, tup):

        """takes a whole database row, does the int-to-tag conversion and returns a namedtuple"""

        args = [x for x in tup]
        score_1 = args[8]  # have to unpack the tuple and convert g- and score_2s to tag lists
        score_2 = args[9]  # TODO: unpack by NAME, not INDEX
        tag_group_1, tag_group_2 = self.ints_to_tags(score_1, score_2)
        args[8] = tag_group_1
        args[9] = tag_group_2
        return self.dbrow(*args)

    def get_directories(self):

        """Returns the list of all possible top-level directories for filtering purposes"""

        print("Getting distinct directories...")
        self.db_cursor.execute('''select distinct directory from videos''')
        # this query returns every distinct possible value in the column
        return [x[0] for x in self.db_cursor.fetchall()]  # unpack the tuples

    def get_icons(self):

        """returns the left and right arrow and placeholder image in this exact order"""

        out = []

        for name in ["left_arrow", "right_arrow", "placeholder"]:
            with open(f"{name}.gif", "rb") as f:
                img = f.read()
                out.append(img)

        return out

    def check_has_thumbnail(self, fullpath):

        """Return true if a thumbnail blob exists"""

        # self.db_cursor.execute('''select thumbnail from videos where fullpath = ? and thumbnail not null''',
        #                       (fullpath,))   # old database structure
        self.db_cursor.execute('''select thumbnail from thumbnails
                                where fullpath = ?
                                and thumbnail not null''', (fullpath,))

        res = self.db_cursor.fetchone()

        if not res:
            return False
        else:
            return True

    def path_generator(self, directory, random=False):

        """Successive fullpaths to the tagging interface so that tagging
        is based on existing DB entries and not walking the directory structure

        This function skips over entries with the 'skipped' flag set

        returns a list having fetchall'ed from the db cursor"""

        if random is False:
            self.db_cursor.execute('''select fullpath from videos 
            where directory = ? 
            and skipped is not 1
            and score_1 is null
            and score_2 is null''', (directory,))
        else:
            self.db_cursor.execute('''select fullpath from videos 
            where skipped is not 1
            and score_1 is null
            and score_2 is null
            order by created desc''')
            # and width > 959  additional constraint for only HD stuff

            # and duration not null
            # and duration > 420  additional contstraints cut out

        return [x[0] for x in self.db_cursor.fetchall()]

        # have to unpack the whole thing otherwise SQL will complain about being
        # called from another thread

    def remove_directory_filter(self):

        """unsets the filtering"""

        self.filter_directory = None

    def set_directory_filter(self, path):

        """only returns results from within this top level dir
        these dirs correspond to values in the DB"""

        self.filter_directory = path

    def check_if_new_file(self, fullpath):

        """New fullpath has been found that is not in DB - check to see if the new file
        is duplicate (using size/hash comparison) or check if an old file was moved"""

        bits = fullpath.split("\\")
        directory = bits[1]
        dupe = False
        if directory == "$RECYCLE.BIN":
            return False

        new_file_size = os.stat(fullpath).st_size
        self.db_cursor.execute('''select fullpath from videos where filesize = ?''', (new_file_size,))
        found = self.db_cursor.fetchall()
        if found:
            print("Found matching filesize, checking hash")
            this_hash = self.get_file_hash(fullpath)
            for qa in found:
                print(qa)
                found_path = qa[0]
                try:
                    fhash = self.get_file_hash(found_path)

                except FileNotFoundError:
                    print("File {} no longer exists, updating entry".format(found_path))
                    self.db_cursor.execute('''
                    update videos 
                    set fullpath = ?,
                    filename = ? 
                    where fullpath = ?''', (fullpath, os.path.split(fullpath)[-1], found_path,))
                    print("New file location is {}".format(fullpath))
                    dupe = True
                    break
                if fhash == this_hash:
                    print("New file %s already exists at %s (matching hash and size)"
                          % (fullpath, found_path))
                    report = f"{fullpath}\t{found_path}\n"
                    fname = f"dupe_report_{get_today_date()}.csv"
                    # note two files will be created if dupe checking happens across midnight
                    with open(fname, "a") as f:
                        f.write(report)

                    dupe = True
                    break
        else:
            dupe = False

        if dupe:
            print("File already exists and was not added")
            return False
        else:
            print("{} is a new file".format(fullpath))
            return True

    def scan_for_new_files(self, toplevel):

        """walks the entirety of toplevel. If files are found with allowed extensions,
        new entries are created for them in the db."""

        added = 0
        self.db_cursor.execute('''select fullpath from videos''')
        known = set([x[0] for x in self.db_cursor.fetchall()])  # better than looking up each indivudal name in SQL
        verified = set()  # used at end to check if any files are missing
        for head, folders, files in os.walk(toplevel):
            # print(f"{head}, {folders}, {files}")
            if "__" in head:
                # print("Skipped folder {}".format(head))
                continue  # skip folders prefixed with __
            for filename in files:
                _, ext = os.path.splitext(filename)
                if ext.lower() not in self.extensions:
                    continue
                fullpath = os.path.join(head, filename)
                if fullpath in known:
                    verified.add(fullpath)
                    continue

                if self.check_if_new_file(fullpath):
                    created = os.path.getctime(fullpath)
                    fhash = self.get_file_hash(fullpath)
                    fsize = os.stat(fullpath).st_size
                    bits = fullpath.split("\\")
                    dur, unused = VideoObject.get_initial_info(fullpath)
                    directory = bits[1]
                    resx, resy = self.get_video_res(fullpath)
                    self.db_cursor.execute('''insert into videos (
                                            fullpath,
                                            filename,
                                            filesize,
                                            directory,
                                            created,
                                            md5,
                                            duration,
                                            width,
                                            height,
                                            times_viewed) values
                                            (?,?,?,?,?,?,?,?,?,?)''', (fullpath, filename, fsize,
                                                                       directory, created, fhash, dur, resx, resy, 0))
                    self.db_cursor.execute('''insert into thumbnails (fullpath) values (?)''', (fullpath,))
                    # need to insert it into info table AND thumbnail table
                    # print("Made new db entry for {}".format(filename))
                    added += 1
                    known.add(fullpath)  # need to add it to the set otherwise walker will try to add multiple times
                    verified.add(fullpath)
                else:
                    try:
                        move(fullpath, DUPES_FOLDER)
                        print(f"{fullpath} is not new and was moved to the dupes folder.")
                    except Exception as e:
                        print(e)
                    verified.add(fullpath)
                    continue

        print("Added {} new entries".format(added))

        missing = known - verified

        if missing:
            print("Removing missing videos")
            for x in missing:
                self.remove_video(x)

        self.db.commit()

    def get_file_hash(self, fullpath):

        print("Hashing {}...".format(fullpath))
        hasher = md5()
        with open(fullpath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_video_res(self, fullpath):

        """Using the videoobject staticmethod to get vid resolution"""

        res = VideoObject.get_video_res(fullpath)
        try:
            w, h = res.split("x")
        except ValueError:  # ffprobe couldn't get the dimensions
            w = h = 0

        return int(w), int(h)

    def remove_video(self, fullpath):

        """Moves an entry from the videos table to the removed table, for when the file was not found"""

        removal_time = time.time()
        self.db_cursor.execute('''insert into removed 
        (fullpath, filename, filesize) 
        select fullpath,filename,filesize 
        from videos where fullpath = ?''', (fullpath,))
        self.db_cursor.execute('''update removed set deletion_date = ? where fullpath = ?''', (removal_time, fullpath))
        self.db_cursor.execute('''delete from videos where fullpath = ?''', (fullpath,))

        print("{} was moved to the deletions table".format(fullpath))

    def free_up_space(self, amount):

        """Free space in the main videos directory by moving videos that were skipped for tagging to the trash folder.
        e.g. the destination dir can be on a different drive or just somewhere outside the library."""

        allowed_dirs = iter(DELETION_WHITELIST)  # the allowed directories to delete from
        dirct = next(allowed_dirs)
        self.db_cursor.execute('''select * from videos where skipped = 1 and directory = ? order by filesize''',
                               (dirct,))
        # throw out the smallest videos first
        res = iter(self.db_cursor.fetchall())
        total = 0  # keep track of how much has been deleted and only delete the minimum necessary
        while total < amount:  # amount is bytes of data to free up
            try:
                x = next(res)  # can't use a for loop because we need to check amount deleted after every entry
            except StopIteration:  # time to move to the next directory down
                dirct = next(allowed_dirs)
                self.db_cursor.execute('''select * from videos where skipped = 1 and directory = ? order by filesize''',
                                       (dirct,))
                res = iter(self.db_cursor.fetchall())
                continue  # go back to the top of the loop, there is a chance that this next directory has no skipped
                # files in it so then we'll need to advance to the next directory along
            q = self.dbrow(*x, None)  # passing None as the thumbnail because we don't need it
            # making it into a namedtuple/dbrow means we can now access attributes by column name
            fsize = q.filesize
            fullpath = q.fullpath
            try:
                move(fullpath, TRASH_FOLDER)
                self.remove_video(fullpath)  # may as well do this now as we know it's being "deleted"
                total += fsize
                print(f"Moving files... ({total} / {amount})", end="\r")  # end = carriage return overwrites the line
            except Error as e:  # "Error" comes from the shutil module
                print(e)  # e.g. might run into duplicate file names, just print the exception and do nothing
        print(f"Done, moved {round(total/(1024**3), 2)} GB of data to the trash folder.")
        self.db.commit()

