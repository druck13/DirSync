#!/usr/bin/env python3
###############################################################################
## Directory Synchroniation Client
##
## (C) 2020 David Ruck
###############################################################################

import os
import sys
import time
import argparse
import json
import hashlib
import urllib.parse
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

## Constants ##################################################################

POLL_TIME   = 10                # Interval to poll main thread
API         = "/api/v1.0/"      # v1.0 API url prefix
API1        = "/api/v1.1/"      # v1.1 API url prefix

## Global Variables ###########################################################

server    = "localhost:5000"    # DirSync serve host:port
directory = ""                  # directory to synchronise

## Classes ####################################################################

# Description : Class to handle files system watcher events
class Handler(FileSystemEventHandler):
    # Description : Called for file on directory creation
    # Parameters  : FileSystemHandler event - the event to handle
    # Returns     : None
    @staticmethod
    def on_created(event):
        # Only handle directories, created files will get a subsequent modified event
        if event.is_directory:
            CreateDir(os.path.relpath(event.src_path, directory))

    # Description : Called for file on directory deletion
    # Parameters  : FileSystemHandler event - the event to handle
    # Returns     : None
    @staticmethod
    def on_deleted(event):
        # The server will work out to delete either a file or directory
        DeleteObject(os.path.relpath(event.src_path, directory))

    # Description : Called for file on directory modification
    # Parameters  : FileSystemHandler event - the event to handle
    # Returns     : None
    @staticmethod
    def on_modified(event):
        # Only handle files
        remotefile = os.path.relpath(event.src_path, directory)
        if not event.is_directory and not CheckFile(event.src_path, remotefile):
            CopyFile(event.src_path, remotefile)


    # Description : Called for file on directory renaming
    # Parameters  : FileSystemHandler event - the event to handle
    # Returns     : None
    @staticmethod
    def on_moved(event):
        # if an attempt is made to move the object out of the source directory
        # delete the object instead - doesn't seem to happen on Window or Linux
        # we do get a delete instead, but check nevertheless
        if os.path.commonprefix([event.src_path, directory]) != directory:
            DeleteObject(os.path.relpath(event.src_path, directory))
        else:
            # rename the object
            RenameObject(os.path.relpath(event.src_path,  directory),
                         os.path.relpath(event.dest_path, directory))

## Functions ##################################################################

# Description : Checks a directory exists on the server
# Parameters  : string dirname  - directory name
# Returns     : bool            - True if Exists
def DirExists(dirname):
    response = requests.get(server+API+"direxists/"+urllib.parse.quote(dirname))
    if response.ok:
        return True
    if response.status_code == 410:
        return False
    response.raise_for_status() # Doesn't return
    return False                # Added for pylint


# Description : Checks a file is identical on the serber
# Parameters  : string dirname  - directory name
# Returns     : None
def CreateDir(dirname):
    response = requests.post(server+API+"createdir/"+urllib.parse.quote(dirname))
    if not response.ok:
        response.raise_for_status()


# Description : Checks if a file exists and is identical on the server
# Parameters  : string localfile    - source filename
#               string remotefile   - destination filename
# Returns     : bool                - True if file is on the server
def CheckFile(localfile, remotefile):
    response = requests.get(server+API+"checkfile/"+urllib.parse.quote(remotefile))
    if response.ok:
        data       = json.loads(response.content.decode('utf-8'))
        localstat  = os.stat(localfile)
        remotestat = os.stat_result(data)
        # check file size and modification times match
        return remotestat.st_size  == localstat.st_size and \
               remotestat.st_mtime == localstat.st_mtime
    if response.status_code == 410:
        return False
    response.raise_for_status() # Doesn't return
    return False                # Added for pylint


# Description : Copies a file to the server
# Parameters  : string localfile    - source filename
#               string remotefile   - destination filename
# Returns     : None
def CopyFile(localfile, remotefile):
    localstat = os.stat(localfile)
    localinfo = "&filesize=%d&atime_ns=%d&mtime_ns=%d" % (localstat.st_size, localstat.st_atime_ns, localstat.st_mtime_ns)

    # Try v1.1 API to get checksums of each block of file
    response = requests.get(server+API1+"filesums/"+urllib.parse.quote(remotefile))
    if response.ok:
        remoteinfo = json.loads(response.content.decode('utf-8'))
        blocksize  = remoteinfo['Blocksize']
        block      = 0
        data       = None
        lastsent   = False
        # Read file in blocks using size from server
        with open(localfile, "rb") as f:
            while True:
                data = f.read(blocksize)
                last = len(data) < blocksize
                # Check for EOF
                h = hashlib.sha1()
                h.update(data)

                # If larger than remote file, or checksum doesn't match
                if block >= len(remoteinfo['Checksums']) \
                or h.hexdigest() != remoteinfo['Checksums'][block]:

                    url = server+API1+"copyblock/"+urllib.parse.quote(remotefile)+"?offset="+str(block*blocksize)

                    # Add file information on the last block
                    if last:
                        url     += localinfo
                        lastsent = True

                    #send the block of data
                    response2 = requests.post(url, data=data)
                    if not response2.ok:
                        response2.raise_for_status()

                if last:
                    break
                block += 1
        # if the last block wasn't sent, send the file information
        if not lastsent:
            url = server+API1+"copyblock/"+urllib.parse.quote(remotefile)+"?offset="+str(block*blocksize)+localinfo
            response3 = requests.post(url)
            if not response3.ok:
                response3.raise_for_status()
    # fallback copying while file with v1.0 API
    elif response.status_code == 404:
        print("Server: Copying file: %s" % remotefile)
        # read file in to memory - wont work for massive files
        with open(localfile, "rb") as f:
            data = f.read()

        response  = requests.post(server+API+"copyfile/"+urllib.parse.quote(remotefile)+
                                  "?atime_ns="+str(localstat.st_atime_ns)+
                                  "&mtime_ns="+str(localstat.st_mtime_ns),
                                  data=data)

     # Failure of either API will reach here
    if not response.ok:
        response.raise_for_status()


# Description : Checks a file is identical on the serber
# Parameters  : string name  - file or directory name
# Returns     : None
def DeleteObject(name):
    response = requests.delete(server+API+"deleteobject/"+urllib.parse.quote(name))
    if not response.ok:
        response.raise_for_status()


# Description : Renames a file or directory on the server
# Parameters  : string oldname - existing filename
#               string newname - new filename
# Returns     : None
def RenameObject(oldname, newname):
    response = requests.put(server+API+"renameobject/"+urllib.parse.quote(oldname)+
                            "?newname="+urllib.parse.quote(newname))
    if not response.ok:
        response.raise_for_status()


# Description : Ensure each file in directory is present on server
# Parameters  : string dirname     - directory to scan
# Returns     : None
def SyncDirectory(dirname):
    # Enumerate directory
    for root, dirs, files in os.walk(dirname):
        # path relative to the source directory
        path = os.path.relpath(root, dirname)
        # Handle directories
        for adir in dirs:
            remotedir = os.path.join(path, adir)
            if not DirExists(remotedir):
                CreateDir(remotedir)
        # Handle files
        for file in files:
            localfile  = os.path.join(root, file)
            remotefile = os.path.join(path, file)
            if not CheckFile(localfile, remotefile):
                CopyFile(localfile, remotefile)

## Main #######################################################################

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Directory Synchronisation Client v1.1")
    parser.add_argument("-s", "--server", default=server,  help="Server host:port, defaults to "+server)
    parser.add_argument("directory",                       help="directory to synchronise")
    args = parser.parse_args()

    server    = "http://"+args.server
    directory = os.path.realpath(args.directory)

    # Check directory exists
    if not os.path.isdir(args.directory):
        sys.stderr.write("Client: Directory does not exist: %s\n" % directory)
        sys.exit(1)

    # Wait for sever to start
    print("Client: Waiting for server to start...")
    while True:
        try:
            response = requests.get(server+API)
            # proceed after any response
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            time.sleep(1)

    # Initial Sync of directory on starting
    SyncDirectory(directory)

    # Start watching the directory
    event_handler = Handler()
    observer      = Observer()
    observer.schedule(event_handler, directory, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(POLL_TIME)
    except KeyboardInterrupt:
        observer.stop()
        print("Client: Terminated by the user")
    finally:
        observer.join()

## EOF ########################################################################
