#!/usr/bin/env python3
###############################################################################
## Directory Synchronization Client
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

POLL_TIME   = 1                     # Interval to poll main thread
API         = "/api/v1.0/"          # v1.0 API url prefix
API1        = "/api/v1.1/"          # v1.1 API url prefix

## Global Variables ###########################################################

server      = "localhost:5000"      # DirSync server host:port
directory   = ""                    # directory to synchronise
updatemax   = 60                    # Default file update limit in seconds
timeout     = 10                    # request timeout in seconds

updatedict  = {}                    # Dictionary file update information
                                    # { <filename> : { 'LastUpdated'   : <time>,
                                    #                  'UpdatePending' : True|False }}


## Classes ####################################################################

# Description : Class to handle files system watcher events
class Handler(FileSystemEventHandler):
    def on_created(self, event):
        """
        Called for file or directory creation
        :param event: FileSystemHandler event to handle
        """
        # Only handle directories, created files will get a subsequent modified event
        if event.is_directory:
            create_dir(os.path.relpath(event.src_path, directory))


    # Description :
    # Parameters  : FileSystemHandler event - the event to handle
    # Returns     : None
    def on_deleted(self, event):
        """
        Called for file or directory deletion
        :param event: FileSystemHandler event to handle
        :return:
        """
        if event.src_path in updatedict:
            # throw away any pending updates on deletion
            del updatedict[event.src_path]
        # The server will work out to delete either a file or directory
        delete_object(os.path.relpath(event.src_path, directory))


    # Description : Called for file on directory modification
    # Parameters  : FileSystemHandler event - the event to handle
    # Returns     : None
    def on_modified(self, event):
        """
        Called for file on directory modification
        :param event: FileSystemHandler event to handle
         """
        # Only handle files
        if not event.is_directory:
            # check if updated previously, otherwise copy now
            if event.src_path in updatedict:
                updatedict[event.src_path]['PendingUpdate'] = True
            else:
                copy_file(event.src_path, os.path.relpath(event.src_path, directory))
                updatedict[event.src_path] = { 'LastUpdated' : time.time(), 'PendingUpdate' : False }


    # Description : Called for file on directory renaming
    # Parameters  : FileSystemHandler event - the event to handle
    # Returns     : None
    def on_moved(self, event):
        """
        Called for file on directory renaming
        :param event: FileSystemHandler event to handle
        """
        # if an attempt is made to move the object out of the source directory
        # delete the object instead - doesn't seem to happen on Windows or Linux
        # we do get a delete command instead, but check nevertheless
        if os.path.commonprefix([event.src_path, directory]) != directory:
            delete_object(os.path.relpath(event.src_path, directory))
        else:
            # rename the object
            rename_object(os.path.relpath(event.src_path, directory),
                          os.path.relpath(event.dest_path, directory))
            # rename file in update dict too
            if event.src_path in updatedict:
                updatedict[event.dest_path] = updatedict[event.src_path]
                del updatedict[event.src_path]

## Functions ##################################################################

def dir_exists(dirname):
    """
    Checks a directory exists on the server
    :param dirname: directory name
    :type dirname: string
    :return: True if Exists
    :rtype: bool
    """
    response = requests.get(server+API+"direxists/"+urllib.parse.quote(dirname), timeout=timeout)
    if response.ok:
        return True
    if response.status_code == 410:
        return False
    response.raise_for_status() # Doesn't return if error
    return False                # Added for pylint


def create_dir(dirname):
    """
    Checks a file is identical on the server
    :param dirname: directory name
    :type dirname: string
    """
    response = requests.post(server+API+"createdir/"+urllib.parse.quote(dirname), timeout=timeout)
    response.raise_for_status()


def check_file(localfile, remotefile):
    """
    Checks if a file exists and is identical on the server
    :param localfile: source filename
    :type localfile: string
    :param remotefile: destination filename
    :type remotefile: string
    :return: True if file is on the server
    :rtype: bool
    """
    response = requests.get(server+API+"checkfile/"+urllib.parse.quote(remotefile), timeout=timeout)
    if response.ok:
        data       = json.loads(response.content.decode('utf-8'))
        localstat  = os.stat(localfile)
        remotestat = os.stat_result(data)
        # check file size and modification times match
        return remotestat.st_size  == localstat.st_size and \
               remotestat.st_mtime == localstat.st_mtime
    if response.status_code == 410:
        return False
    response.raise_for_status() # Doesn't return if error
    return False                # Added for pylint


def copy_file(localfile, remotefile):
    """
    Copies a file to the server
    :param localfile: source filename
    :type localfile: string
    :param remotefile:  destination filename
    :type remotefile: string
    """
    # Try v1.1 API to get checksums of each block of file
    response = requests.get(server+API1+"filesums/"+urllib.parse.quote(remotefile), timeout=timeout)
    if response.ok:
        remoteinfo = json.loads(response.content.decode('utf-8'))
        blocksize  = remoteinfo['Blocksize']
        block      = 0
        lastsent   = False
        # Read file in blocks using blocksize from server
        with open(localfile, "rb") as f:
            while True:
                data = f.read(blocksize)
                # Check for EOF
                if not data:
                    break

                # short block indicates last
                last = len(data) < blocksize

                h = hashlib.sha1()
                h.update(data)

                # If larger than remote file, or checksum doesn't match
                if block >= len(remoteinfo['Checksums']) \
                or h.hexdigest() != remoteinfo['Checksums'][block]:
                    url    = server+API1+"copyblock/"+urllib.parse.quote(remotefile)
                    query = { "offset" : str(block*blocksize) }
                    # Add file information on the last block
                    if last:
                        localstat = os.stat(localfile)
                        query.update({"filesize" : localstat.st_size,
                                      "atime_ns" : localstat.st_atime_ns,
                                      "mtime_ns" : localstat.st_mtime_ns})
                        lastsent  = True

                    #send the block of data
                    response2 = requests.post(url, data=data, params=query, timeout=timeout)
                    response2.raise_for_status()

                block += 1
        # if the last block wasn't sent (file was a multiple of block size)
        # send the file information without any data
        if not lastsent:
            localstat = os.stat(localfile)
            url       = server+API1+"copyblock/"+urllib.parse.quote(remotefile)
            query     = { "offset"   : block*blocksize,
                          "filesize" : localstat.st_size,
                          "atime_ns" : localstat.st_atime_ns,
                          "mtime_ns" : localstat.st_mtime_ns }
            response3 = requests.post(url, params=query, timeout=timeout)
            response3.raise_for_status()

    # fallback copying while file with v1.0 API
    elif response.status_code == 404:
        print("Server: Copying file: %s" % remotefile)
        # read file in to memory - won't work for massive files
        localstat = os.stat(localfile)
        with open(localfile, "rb") as f:
            data = f.read()

        response  = requests.post(server+API+"copyfile/"+urllib.parse.quote(remotefile),
                                  params={ "atime_ns" : localstat.st_atime_ns,
                                           "mtime_ns" : localstat.st_mtime_ns },
                                  data=data,
                                  timeout=timeout)

    # Failure of either API will reach here
    response.raise_for_status()


def delete_object(name):
    """
    Checks a file is identical on the server
    :param name: file or directory name
    :type name: string
    """
    response = requests.delete(server+API+"deleteobject/"+urllib.parse.quote(name), timeout=timeout)
    response.raise_for_status()


def rename_object(oldname, newname):
    """
    Renames a file or directory on the server
    :param oldname: existing filename
    :type oldname: string
    :param newname: new filename
    :type newname: string
    """
    response = requests.put(server+API+"renameobject/"+urllib.parse.quote(oldname),
                            params={"newname" : urllib.parse.quote(newname)},
                            timeout=timeout)
    response.raise_for_status()


def sync_directory(dirname):
    """
    Ensure each file in directory is present on server
    Used at client startup for initial synchronisation
    :param dirname: directory to scan
    :type dirname: string
    """
    # Enumerate directory
    for root, dirs, files in os.walk(dirname):
        # path relative to the source directory
        path = os.path.relpath(root, dirname)
        # Handle directories
        for adir in dirs:
            remotedir = os.path.join(path, adir)
            if not dir_exists(remotedir):
                create_dir(remotedir)
        # Handle files
        for file in files:
            localfile  = os.path.join(root, file)
            remotefile = os.path.join(path, file)
            if not check_file(localfile, remotefile):
                copy_file(localfile, remotefile)

## Main #######################################################################

def main():
    global server, directory
    parser = argparse.ArgumentParser(description="Directory Synchronisation Client v1.2")
    parser.add_argument("-s", "--server",              default=server,     help="Server host:port, defaults to "+server)
    parser.add_argument("-u", "--updatemax", type=int, default=updatemax,  help="Only update a file once per interval, defaults to "+str(updatemax)+" seconds")
    parser.add_argument("directory",                                       help="directory to synchronise")
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
            requests.get(server+API, timeout=timeout)
            # proceed after any response
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            time.sleep(1)

    # Initial Sync of directory on starting
    sync_directory(directory)

    # Start watching the directory
    event_handler = Handler()
    observer      = Observer()
    observer.schedule(event_handler, directory, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(POLL_TIME)

            # scan the update dict
            for name in list(updatedict):
                # act after the update interval has elapsed
                if time.time() - updatedict[name]['LastUpdated'] >= args.updatemax:
                    if updatedict[name]['PendingUpdate']:
                        # Perform the pending update, and record last update time
                        copy_file(name, os.path.relpath(name, directory))
                        updatedict[name] = { 'LastUpdated' : time.time(), 'PendingUpdate' : False }
                    else:
                        # No updates, so forget file
                        del updatedict[name]
    except KeyboardInterrupt:
        observer.stop()
        print("Client: Terminated by the user")
    finally:
        observer.join()

if __name__ == '__main__':
    main()

## EOF ########################################################################
