#!/usr/bin/env python3
###############################################################################
## Directory Synchroniation Server
##
## (C) 2020 David Ruck
###############################################################################

import os
import argparse
import urllib.parse
import signal
import logging
import hashlib
import flask

## Constants ##################################################################

API       = "/api/v1.0"         # v1.0 API url prefix
API1      = "/api/v1.1"         # v1.1 API url prefix
INTERFACE = "localhost:5000"    # host:port to bind server to
DIRECTORY = "Storage"           # Name of directory to synchronise to
BLOCKSIZE = 256 * 1024          # Size of block for file change detection

## Functions ##################################################################

## API Functions --------------------------------------------------------------

class DirSyncServer:
    def __init__(self, server_directory):
        self.directory = server_directory

        if not os.path.isdir(self.directory):
            print("Server: Creating directory: %s" % self.directory)
            os.makedirs(self.directory)

        self.app = flask.Flask("DirSync")
        self.app.add_url_rule(API  + "/direxists/<path:dirname>",    "DirExists", self.dir_exists,    methods=["GET"])
        self.app.add_url_rule(API  + "/createdir/<path:dirname>",    "CreateDir", self.create_dir,    methods=["POST"])
        self.app.add_url_rule(API  + "/checkfile/<path:filename>",   "CheckFile", self.check_file,    methods=["GET"])
        self.app.add_url_rule(API1 + "/filesums/<path:filename>",    "FileSums",  self.file_sums,     methods=["GET"])
        self.app.add_url_rule(API  + "/copyfile/<path:filename>",    "CopyFile",  self.copy_file,     methods=["POST"])
        self.app.add_url_rule(API1 + "/copyblock/<path:filename>",   "CopyBlock", self.copy_block,    methods=["POST"])
        self.app.add_url_rule(API  + "/deleteobject/<path:name>",    "DeleteObj", self.delete_object, methods=["DELETE"])
        self.app.add_url_rule(API  + "/renameobject/<path:oldname>", "RenameObj", self.rename_object, methods=["PUT"])
        self.app.add_url_rule(API  + "/shutdown",                    "Shutdown",  self.shutdown,      methods=["POST"])

    def dir_exists(self, dirname):
        """
        Checks a directory exists on the server
        :param dirname: directory name from URL
        :type dirname: string
        :return: True if Exists
        :rtype: bool
        """
        dirname = os.path.join(self.directory, urllib.parse.unquote(dirname))
        if not os.path.isdir(dirname):
            flask.abort(410)
        return flask.make_response("Exists", 200)

    def create_dir(self, dirname):
        """
        Checks a file is identical on the server
        :param dirname: directory name from URL
        :type dirname: string
        """
        dirname = os.path.join(self.directory, urllib.parse.unquote(dirname))
        try:
            print("Server: Creating directory: %s" % dirname)
            os.makedirs(dirname, exist_ok=True)
            return flask.make_response("Created", 200)
        except IOError as e:
            print("Server: Creating directory failed: %s :%s" % (dirname, str(e)))
            return flask.abort(403)

    def check_file(self, filename):
        """
        Checks if a file exists and returns stat information
        :param filename: filename to check from url
        :type filename: string
        """
        filename = os.path.join(self.directory, urllib.parse.unquote(filename))
        if not os.path.isfile(filename):
            flask.abort(410)
        return flask.jsonify(os.stat(filename))

    def file_sums(self, filename):
        """
        Gets checksums for each block of data in a file
        Sends back the file size and list of checksum values
        :param filename: filename from url
        :type filename: string
        """
        filename = os.path.join(self.directory, urllib.parse.unquote(filename))

        checksums = []

        if os.path.isfile(filename):
            # Read the file in blocks and add checksums to list
            with open(filename, "rb") as f:
                while True:
                    data = f.read(args.blocksize)
                    # check for EOF
                    if not data:
                        break
                    h = hashlib.sha1()
                    h.update(data)
                    checksums.append(h.hexdigest())


        # if file doesn't exist just block size and empty list will be sent
        fileinfo = \
        {
            'Blocksize' : args.blocksize,
            'Checksums' : checksums
        }
        return flask.jsonify(fileinfo)

    def copy_file(self, filename):
        """
        Writes a file
        access and modification times come from url arguments
        file data is encoded in the request
        :param filename: filename from url
        :type filename: string
        """
        filename = os.path.join(self.directory, urllib.parse.unquote(filename))
        atime_ns = flask.request.args.get('atime_ns')
        mtime_ns = flask.request.args.get('mtime_ns')
        try:
            print("Server: Copying file: %s" % filename)
            with open(filename, "wb") as f:
                f.write(flask.request.get_data())

            # Set the access and modification times, for use by initial directory sync
            if atime_ns and mtime_ns:
                os.utime(filename, ns=(int(atime_ns), int(mtime_ns)))
            return flask.make_response("Copied", 200)
        except IOError as e:
            print("Server: Copy failed: %s" % str(e))
            return flask.abort(403)

    def copy_block(self, filename):
        """
        Writes a block of a file
        offset, file size, access and mofication times come from url arguments
        file data is encoded in the request
        :param filename: filename from url
        :type filename: string
        """
        filename = os.path.join(self.directory, urllib.parse.unquote(filename))
        offset   = int(flask.request.args.get('offset'))
        filesize = flask.request.args.get('filesize')
        atime_ns = flask.request.args.get('atime_ns')
        mtime_ns = flask.request.args.get('mtime_ns')
        try:
            print("Server: Copying file block: %s offset %d %s" % (filename, offset, "size "+filesize if filesize else ""))
            with open(filename, "rb+" if os.path.isfile(filename) else "wb") as f:
                # Write the block at the given offset
                f.seek(offset)
                f.write(flask.request.get_data())

                # Ensure the file is set to the new size
                if filesize:
                    f.truncate(int(filesize))

            # Set the access and modification times, for use by initial directory sync
            if atime_ns and mtime_ns:
                os.utime(filename, ns=(int(atime_ns), int(mtime_ns)))
            return flask.make_response("Written", 200)
        except IOError as e:
            print("Server: Write failed: %s" % str(e))
            return flask.abort(403)

    def delete_object(self, name):
        """
        Deletes a file or directory on the server
        :param name: file or directory name from url
        :type name: string
        """
        name = os.path.join(self.directory, urllib.parse.unquote(name))
        try:
            if os.path.isdir(name):
                print("Server: Deleting directory: %s" % name)
                os.rmdir(name)
            elif os.path.isfile(name):
                print("Server: Deleting file: %s" % name)
                os.remove(name)
            else:
                print("Server: Invalid name to delete: %s" % name)
            return flask.make_response("Nothing to delete", 200)
        except IOError as e:
            print("Server: Deletion failed: %s" % str(e))
            return flask.abort(403)

    def rename_object(self, oldname):
        """
        Renames a file or directory on the server
        new file name comes from url newname argument
        :param oldname: existing filename from url
        :type oldname: string
        """
        newname = flask.request.args.get('newname')
        if not newname:
            flask.abort(400)
        oldname = os.path.join(self.directory, urllib.parse.unquote(oldname))
        newname = os.path.join(self.directory, urllib.parse.unquote(newname))
        try:
            print("Server: Renaming from %s to %s" % (oldname, newname))
            os.rename(oldname, newname)
            return flask.make_response("Renamed", 200)
        except FileNotFoundError:
            # ignore file not found as can be sent notifications for
            # the contents of directories which have been renamed
            return flask.make_response("Not renamed", 200)
        except IOError as e:
            print("Server: Rename failed: %s" % str(e))
            return flask.abort(403)

    @staticmethod
    def shutdown():
        """
        shutdown the server
        used when run over ssh by test suite as flask ignores sighup
        """
        # Send ourself a keyboard interrupt signal to quit
        os.kill(os.getpid(), signal.SIGINT)
        return flask.make_response("Shutting down", 200)

## Main #######################################################################

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Directory Synchronisation Server v1.2")
    parser.add_argument("-i", "--interface", default=INTERFACE, help="Interface to bind to, defaults to " + INTERFACE)
    parser.add_argument("-b", "--blocksize", type=int, default=BLOCKSIZE, help="Block size for file change detection, defaults to " + str(BLOCKSIZE) + " bytes")
    parser.add_argument("directory", nargs='?', default=DIRECTORY, help="Directory to synchronise")
    args = parser.parse_args()

    # Disable most logging by flask
    logging.getLogger('werkzeug').disabled = True

    # Get host:port, or just host
    parts = args.interface.split(':')
    if len(parts) > 1:
        host = parts[0]
        port = parts[1]
    else:
        host = args.interface
        port = None

    server = DirSyncServer(args.directory)

    try:
        # Start the flask server
        server.app.run(host=host, port=port, debug=False)
    except KeyboardInterrupt:
        print("Server: Terminated by the user")

## EOF ########################################################################
