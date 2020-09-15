#!/usr/bin/env python3
###############################################################################
## Directory Synchroniation Server
##
## (C) 2020 David Ruck
###############################################################################

import os
import sys
import time
import argparse
import urllib.parse
import logging
import flask

## Constants ##################################################################

API = "/api/v1.0"              # API url prefix

## Global Variables ###########################################################

app       = flask.Flask("DirSync")
interface = "localhost:5000"    # host:port to bind server to
directory = "Storage"           # Name of directory to synchronise to

## Functions ##################################################################

# Description : Checks a directory exists on the server
# Parameters  : string dirname  - directory name from URL
# Returns     : bool            - True if Exists
@app.route(API+"/direxists/<path:dirname>", methods=["GET"])
def DirExists(dirname):
    dirname = os.path.join(directory, urllib.parse.unquote(dirname))
    if not os.path.isdir(dirname):
        flask.abort(404)
    return flask.make_response("Exists", 200)


# Description : Checks a file is identical on the serber
# Parameters  : string dirname  - directory name from URL
# Returns     : None
@app.route(API+"/createdir/<path:dirname>", methods=["POST"])
def CreateDir(dirname):
    dirname = os.path.join(directory, urllib.parse.unquote(dirname))
    try:
        print("Server: Creating directory: %s" % dirname)
        os.makedirs(dirname, exist_ok=True)
        return flask.make_response("Created", 200)
    except IOError as e:
        print("Server: Creating directory failed: %s :%s" % (dirname, str(e)))
        flask.abort(404)


# Description : Checks if a file exists and returns stat information
# Parameters  : string filename - filename to check
# Returns     : None
@app.route(API+"/checkfile/<path:filename>", methods=["GET"])
def CheckFile(filename):
    filename = os.path.join(directory, urllib.parse.unquote(filename))
    if not os.path.isfile(filename):
        flask.abort(404)
    return flask.jsonify(os.stat(filename))


# Description : Copies a file to the server
# Parameters  : string localfile    - source filename
#               string remotefile   - destination filename
# Returns     : None
def CopyFile(localfile, remotefile):
    print("Server: Copying file: %s" % remotefile)
    shutil.copy(localfile, os.path.join(directory, remotefile))


# Description : Checks a file is identical on the serber
# Parameters  : string name  - file or directory name
# Returns     : None
@app.route(API+"/deleteobject/<path:name>", methods=["DELETE"])
def DeleteObject(name):
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
        print("Server: Deletion failed: %s :%s" % (name, str(e)))
        flask.abort(404)


# Description : Renames a file or directory on the server
# Parameters  : string oldname - existing filename
#               string newname - new filename
# Returns     : None
def RenameObject(oldname, newname):
    print("Server: Renaming from %s to %s" % (oldname, newname))
    os.rename(os.path.join(directory, oldname), os.path.join(directory, newname))


## Main #######################################################################

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Directory Synchronisation Server")
    parser.add_argument("-i", "--interface",        default=interface,  help="Interface to bind to, defaults to "+interface)
    parser.add_argument("directory",    nargs='?',  default=directory,  help="directory to synchronise")
    args = parser.parse_args()

    # Set global for storage directory
    directory = args.directory

    if not os.path.isdir(directory):
        print("Server: Creating directory: %s" % directory)
        os.makedirs(directory)

    try:
        # Disable most logging by flask
        log = logging.getLogger("DirSync")
        log.disabled = True
        app.logger.disabled = True

        # Get host:port, or just host
        parts = args.interface.split(':')
        if len(parts) > 1:
            host = parts[0]
            port = parts[1]
        else:
            host = args.interface
            port = None
        app.run(host=host, port=port, debug=False)
    except KeyboardInterrupt:
        print("Server: Terminated by the user")

## EOF ########################################################################
