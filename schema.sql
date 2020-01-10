CREATE TABLE "videos" ( "fullpath" text, "filename" text, "filesize" integer, "directory" string,
"created" real, "skipped" integer, "width" integer, "height" integer,
"score_1" integer, "score_2" integer,
"md5" text, "duration" REAL, "times_viewed" integer,
"tagged_when" integer,
PRIMARY KEY("fullpath") );

CREATE TABLE "tag_group_1" ( "tag" TEXT, "value" integer );

CREATE TABLE "tag_group_2" ( "tag" TEXT, "value" integer );

CREATE TABLE "thumbnails" ( "fullpath" text, "thumbnail" blob, PRIMARY KEY("fullpath") );

CREATE TABLE "removed" (fullpath text, filename text, filesize integer, deletion_date real);

-- CREATE TABLE "icons" ( "name" TEXT, "image" BLOB );  -- seperate files

-- CREATE TABLE "extensions" (extension string); -- this is now in settings.json



