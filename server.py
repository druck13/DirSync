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
        os.makedirs(dirname)
        return flask.make_response("Created", 200)
    except IOError as e:
        print("Server: Creating directory failed: %s :%s" % (dirname, str(e)))
        flask.abort(404)


# Description : Checks if a file exists and is identical on the server
# Parameters  : string localfile    - source filename
#               string remotefile   - destination filename
# Returns     : bool                - True if file is on the server
def CheckFile(localfile, remotefile):
    remotefile = os.path.join(directory, remotefile)
    if not os.path.isfile(remotefile):
        return False

    localstat  = os.stat(localfile)
    remotestat = os.stat(remotefile)

    # check file size and modification times match
    return remotestat.st_size  == localstat.st_size and \
           remotestat.st_mtime == localstat.st_mtime


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
def DeleteObject(name):
    name = os.path.join(directory,  name)
    if os.path.isdir(name):
        print("Server: Deleting directory: %s" % name)
        os.rmdir(name)
    elif os.path.isfile(name):
        print("Server: Deleting file: %s" % name)
        os.remove(name)
    else:
        print("Server: Invalid name to delete: %s" % name)


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
