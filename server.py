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

API = "/api/v1.0"              # v1.0 API url prefix
API1 = "/api/v1.1"             # v1.1 API url prefix

## Global Variables ###########################################################

app       = flask.Flask("DirSync")
interface = "localhost:5000"    # host:port to bind server to
directory = "Storage"           # Name of directory to synchronise to
blocksize = 256*1024            # Size of block for file change detection

## Functions ##################################################################

## API Functions --------------------------------------------------------------

@app.route(API+"/direxists/<path:dirname>", methods=["GET"])
def dir_exists(dirname):
    """
    Checks a directory exists on the server
    :param dirname: directory name from URL
    :type dirname: string
    :return: True if Exists
    :rtype: bool
    """
    dirname = os.path.join(directory, urllib.parse.unquote(dirname))
    if not os.path.isdir(dirname):
        flask.abort(410)
    return flask.make_response("Exists", 200)


@app.route(API+"/createdir/<path:dirname>", methods=["POST"])
def create_dir(dirname):
    """
    Checks a file is identical on the server
    :param dirname: directory name from URL
    :type dirname: string
    """
    dirname = os.path.join(directory, urllib.parse.unquote(dirname))
    try:
        print("Server: Creating directory: %s" % dirname)
        os.makedirs(dirname, exist_ok=True)
        return flask.make_response("Created", 200)
    except IOError as e:
        print("Server: Creating directory failed: %s :%s" % (dirname, str(e)))
        return flask.abort(403)


@app.route(API+"/checkfile/<path:filename>", methods=["GET"])
def check_file(filename):
    """
    Checks if a file exists and returns stat information
    :param filename: filename to check from url
    :type filename: string
    """
    filename = os.path.join(directory, urllib.parse.unquote(filename))
    if not os.path.isfile(filename):
        flask.abort(410)
    return flask.jsonify(os.stat(filename))


@app.route(API1+"/filesums/<path:filename>", methods=["GET"])
def file_sums(filename):
    """
    Gets checksums for each block of data in a file
    Sends back the file size and list of checksum values
    :param filename: filename from url
    :type filename: string
    """
    filename = os.path.join(directory, urllib.parse.unquote(filename))

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


@app.route(API+"/copyfile/<path:filename>", methods=["POST"])
def copy_file(filename):
    """
    Writes a file
    access and modification times come from url arguments
    file data is encoded in the request
    :param filename: filename from url
    :type filename: string
    """
    filename = os.path.join(directory, urllib.parse.unquote(filename))
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


@app.route(API1+"/copyblock/<path:filename>", methods=["POST"])
def copy_block(filename):
    """
    Writes a block of a file
    offset, file size, access and mofication times come from url arguments
    file data is encoded in the request
    :param filename: filename from url
    :type filename: string
    """
    filename = os.path.join(directory, urllib.parse.unquote(filename))
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


@app.route(API+"/deleteobject/<path:name>", methods=["DELETE"])
def delete_object(name):
    """
    Deletes a file or directory on the server
    :param name: file or directory name from url
    :type name: string
    """
    name = os.path.join(directory, urllib.parse.unquote(name))
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


@app.route(API+"/renameobject/<path:oldname>", methods=["PUT"])
def rename_object(oldname):
    """
    Renames a file or directory on the server
    new file name comes from url newname argument
    :param oldname: existing filename from url
    :type oldname: string
    """
    newname = flask.request.args.get('newname')
    if not newname:
        flask.abort(400)
    oldname = os.path.join(directory, urllib.parse.unquote(oldname))
    newname = os.path.join(directory, urllib.parse.unquote(newname))
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


@app.route(API+"/shutdown", methods=["POST"])
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
    parser.add_argument("-i", "--interface",            default=interface,  help="Interface to bind to, defaults to "+interface)
    parser.add_argument("-b", "--blocksize", type=int,  default=blocksize,  help="Block size for file change detection, defaults to "+str(blocksize)+" bytes")
    parser.add_argument("directory",         nargs='?', default=directory,  help="Directory to synchronise")
    args = parser.parse_args()

    # Set global for storage directory
    directory = args.directory

    if not os.path.isdir(directory):
        print("Server: Creating directory: %s" % directory)
        os.makedirs(directory)

    try:
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

        # Start the flask server
        app.run(host=host, port=port, debug=False)
    except KeyboardInterrupt:
        print("Server: Terminated by the user")

## EOF ########################################################################
