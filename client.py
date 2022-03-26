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

POLL_TIME   = 1                     # Interval to poll main thread
API         = "/api/v1.0/"          # v1.0 API url prefix
API1        = "/api/v1.1/"          # v1.1 API url prefix
SERVER      = "localhost:5000"      # DirSync server host:port
UPDATEMAX   = 60                    # Default file update limit in seconds



## Classes ####################################################################

# Description : Class to handle files system watcher events
class DirSynClient(FileSystemEventHandler):
    def __init__(self, server, directory, updatemax):
        self.server     = server
        self.directory  = directory
        self.updatemax  = updatemax
        self.updatedict = {}        # Dictionary file update information
                                    # { <filename> : { 'LastUpdated'   : <time>,
                                    #                  'UpdatePending' : True|False }}
        # Check directory exists
        if not os.path.isdir(self.directory):
            sys.stderr.write("Client: Directory does not exist: %s\n" % self.directory)
            sys.exit(1)

    def on_created(self, event):
        """
        Called for file or directory creation
        :param event: FileSystemHandler event to handle
        """
        # Only handle directories, created files will get a subsequent modified event
        if event.is_directory:
            self.create_dir(os.path.relpath(event.src_path, self.directory))

    def on_deleted(self, event):
        """
        Called for file or directory deletion
        :param event: FileSystemHandler event to handle
        :return:
        """
        if event.src_path in self.updatedict:
            # throw away any pending updates on deletion
            del self.updatedict[event.src_path]
        # The server will work out to delete either a file or directory
        self.delete_object(os.path.relpath(event.src_path, self.directory))

    def on_modified(self, event):
        """
        Called for file on directory modification
        :param event: FileSystemHandler event to handle
         """
        # Only handle files
        if not event.is_directory:
            # check if updated previously, otherwise copy now
            if event.src_path in self.updatedict:
                self.updatedict[event.src_path]['PendingUpdate'] = True
            else:
                self.copy_file(event.src_path, os.path.relpath(event.src_path, self.directory))
                self.updatedict[event.src_path] = { 'LastUpdated' : time.time(), 'PendingUpdate' : False }

    def on_moved(self, event):
        """
        Called for file on directory renaming
        :param event: FileSystemHandler event to handle
        """
        # if an attempt is made to move the object out of the source directory
        # delete the object instead - doesn't seem to happen on Window or Linux
        # we do a delete instead, but check nevertheless
        if os.path.commonprefix([event.src_path, self.directory]) != self.directory:
            self.delete_object(os.path.relpath(event.src_path, self.directory))
        else:
            # rename the object
            self.rename_object(os.path.relpath(event.src_path,  self.directory),
                               os.path.relpath(event.dest_path, self.directory))
            # rename file in update dict too
            if event.src_path in self.updatedict:
                self.updatedict[event.dest_path] = self.updatedict[event.src_path]
                del self.updatedict[event.src_path]

    def dir_exists(self, dirname):
        """
        Checks a directory exists on the server
        :param dirname: directory name
        :type dirname: string
        :return: True if Exists
        :rtype: bool
        """
        response = requests.get(self.server+API+"direxists/"+urllib.parse.quote(dirname))
        if response.ok:
            return True
        if response.status_code == 410:
            return False
        response.raise_for_status() # Doesn't return
        return False                # Added for pylint

    def create_dir(self, dirname):
        """
        Checks a file is identical on the server
        :param dirname: directory name
        :type dirname: string
        """
        response = requests.post(self.server+API+"createdir/"+urllib.parse.quote(dirname))
        if not response.ok:
            response.raise_for_status()

    def check_file(self, localfile, remotefile):
        """
        Checks if a file exists and is identical on the server
        :param localfile: source filename
        :type localfile: string
        :param remotefile: destination filename
        :type remotefile: string
        :return: True if file is on the server
        :rtype: bool
        """
        response = requests.get(self.server+API+"checkfile/"+urllib.parse.quote(remotefile))
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

    def copy_file(self, localfile, remotefile):
        """
        Copies a file to the server
        :param localfile: source filename
        :type localfile: string
        :param remotefile:  destination filename
        :type remotefile: string
        """
        # Try v1.1 API to get checksums of each block of file
        response = requests.get(self.server+API1+"filesums/"+urllib.parse.quote(remotefile))
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
                        url = self.server+API1+"copyblock/"+urllib.parse.quote(remotefile)+"?offset="+str(block*blocksize)
                        # Add file information on the last block
                        if last:
                            localstat = os.stat(localfile)
                            url      += "&filesize="+str(localstat.st_size)+"&atime_ns="+str(localstat.st_atime_ns)+"&mtime_ns="+str(localstat.st_mtime_ns)
                            lastsent  = True

                        #send the block of data
                        response2 = requests.post(url, data=data)
                        if not response2.ok:
                            response2.raise_for_status()

                    block += 1
            # if the last block wasn't sent (file was a multiple of block size)
            # send the file information without any data
            if not lastsent:
                localstat = os.stat(localfile)
                url       = self.server+API1+"copyblock/"+urllib.parse.quote(remotefile)+"?offset="+str(block*blocksize)+ "&filesize="+str(localstat.st_size)+"&atime_ns="+str(localstat.st_atime_ns)+"&mtime_ns="+str(localstat.st_mtime_ns)
                response3 = requests.post(url)
                if not response3.ok:
                    response3.raise_for_status()

        # fallback copying while file with v1.0 API
        elif response.status_code == 404:
            print("Server: Copying file: %s" % remotefile)
            # read file in to memory - won't work for massive files
            localstat = os.stat(localfile)
            with open(localfile, "rb") as f:
                data = f.read()

            response  = requests.post(self.server+API+"copyfile/"+urllib.parse.quote(remotefile)+
                                      "?atime_ns="+str(localstat.st_atime_ns)+
                                      "&mtime_ns="+str(localstat.st_mtime_ns),
                                      data=data)

        # Failure of either API will reach here
        if not response.ok:
            response.raise_for_status()

    def delete_object(self, name):
        """
        Checks a file is identical on the server
        :param name: file or directory name
        :type name: string
        """
        response = requests.delete(self.server+API+"deleteobject/"+urllib.parse.quote(name))
        if not response.ok:
            response.raise_for_status()

    def rename_object(self, oldname, newname):
        """
        Renames a file or directory on the server
        :param oldname: existing filename
        :type oldname: string
        :param newname: new filename
        :type newname: string
        """
        response = requests.put(self.server+API+"renameobject/"+urllib.parse.quote(oldname)+
                                "?newname="+urllib.parse.quote(newname))
        if not response.ok:
            response.raise_for_status()

    def sync_directory(self):
        """
        Ensure each file in directory is present on server
        Used at client startup for initial synchronisation
        """
        # Enumerate directory
        for root, dirs, files in os.walk(self.directory):
            # path relative to the source directory
            path = os.path.relpath(root, self.directory)
            # Handle directories
            for adir in dirs:
                remotedir = os.path.join(path, adir)
                if not self.dir_exists(remotedir):
                    self.create_dir(remotedir)
            # Handle files
            for file in files:
                localfile  = os.path.join(root, file)
                remotefile = os.path.join(path, file)
                if not self.check_file(localfile, remotefile):
                    self.copy_file(localfile, remotefile)

    def wait_for_server(self):
        print("Client: Waiting for server to start...")
        while True:
            try:
                requests.get(self.server + API)
                # proceed after any response
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                time.sleep(1)

    def watch(self):
        event_handler = self
        observer      = Observer()
        observer.schedule(event_handler, self.directory, recursive=True)
        observer.start()

        try:
            while True:
                time.sleep(POLL_TIME)

                # scan the update dict
                for name in list(self.updatedict):
                    # act after the update interval has elapsed
                    if time.time() - self.updatedict[name]['LastUpdated'] >= self.updatemax:
                        if self.updatedict[name]['PendingUpdate']:
                            # Perform the pending update, and record last update time
                            self.copy_file(name, os.path.relpath(name, self.directory))
                            self.updatedict[name] = {'LastUpdated': time.time(), 'PendingUpdate': False}
                        else:
                            # No updates, so forget file
                            del self.updatedict[name]
        except KeyboardInterrupt:
            observer.stop()
            print("Client: Terminated by the user")
        finally:
            observer.join()


## Main #######################################################################

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Directory Synchronisation Client v1.2")
    parser.add_argument("-s", "--server", default=SERVER, help="Server host:port, defaults to " + SERVER)
    parser.add_argument("-u", "--updatemax", type=int, default=UPDATEMAX, help="Only update a file once per interval, defaults to " + str(UPDATEMAX) + " seconds")
    parser.add_argument("directory",                                       help="directory to synchronise")
    args = parser.parse_args()

    client = DirSynClient("http://"+args.server, os.path.realpath(args.directory), args.updatemax)

    # Wait for sever to start
    client.wait_for_server()

    # Initial Sync of directory on starting
    client.sync_directory()

    # Start watching the directory
    client.watch()

## EOF ########################################################################
