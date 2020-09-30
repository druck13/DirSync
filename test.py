#!/usr/bin/env python3
###############################################################################
## Directory Synchroniation Test Suite
##
## (C) 2020 David Ruck
###############################################################################

import os
import sys
import time
import argparse
import shutil
import subprocess
import signal
import hashlib
import requests

## Constants ##################################################################

SERVERSTART_WAIT        = 1             # Time to wait for server to start
TRANSFER_WAIT           = 5             # Time to wait for data transfers
PROCESS_STOP_TIMEOUT    = 10            # Time to wait for program to stop
API                     = "/api/v1.0/"  # v1.0 API url prefix

## Global Variables ###########################################################

# Argument defaults
src_dir         = "Source"              # Name of directory to synchronise from
dest_dir        = "Destination"         # Name of directory to synchronise to
def_dest_dir    = "Storage"             # Default directory used by server
updatemax       = 60                    # default maximum update of files

# Variables used by Test functions
args        = None
client_proc = None
server_proc = None
run         = 0
passed      = 0
failed      = 0

# Test file and directory names
test_dirs  = \
[
    "DirToDelete",
    "DirToRename"
]

test_files = \
[
    "FileToDelete",
    "FileToChangeStart",
    "FileToAdd1",
    "FileToRemove1",
    "FileToReplace",
    "FileToRename",
    os.path.join("DirToDelete", "DirToDeleteFile"),
    os.path.join("DirToDelete", "DirToRenameFile"),
]

## Functions ##################################################################


# Description : Runs the client program
# Parameters  : string hostport - server address and port, or None
#             : string srcdir   - source directory or None
# Returns     : class Popen     - process structure
def StartClient(hostport, srcdir):
    command = [ "python3", "client.py" ]

    if hostport:
        command += [ "--server", hostport ]

    if args.updatemax:
        command += [ "--updatemax", args.updatemax ]

    if srcdir:
        command.append(srcdir)

    print("Starting %s" % " ".join(command))
    return subprocess.Popen(command)


# Description : Stops the client by sending Ctrl+C and waits
# Parameters  : subprocess proc - process structure of program
# Returns     : None
# Exceptions  : subprocess.timeoutexpired if process fails to stop
def StopClient(proc):
    if proc is not None:
        if sys.platform == "win32":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGINT)
        proc.wait(PROCESS_STOP_TIMEOUT)
    # Give remote tasks longer to stop
    if args.command:
        time.sleep(1)


# Description : Runs the server program
# Parameters  : string hostport - server interface or None
#             : string dstdir   - destination directory or None
# Returns     : class Popen     - process structure
def StartServer(hostport, dstdir):
    # User supplied command to start remote server
    if args.command:
        command = args.command.split()
    else:
        command = [ "python3", "server.py" ]

    if hostport:
        command += [ "--interface", hostport ]

    if args.blocksize:
        command += [ "--blocksize", args.blocksize ]

    if dstdir:
        command.append(dstdir)

    print("Starting %s" % " ".join(command))
    ret = subprocess.Popen(command)

    # Wait for server to start before starting client
    time.sleep(SERVERSTART_WAIT)

    return ret

# Description : Stops the server sending a Ctrl+C if running locally
#               or usinf the shutdown APU for a remote server
# Parameters  : subprocess proc - process structure of program
# Returns     : None
# Exceptions  : subprocess.timeoutexpired if process fails to stop
def StopServer(proc):
    if proc is not None:
        # Shutdown a remote server, otherwise will remain running
        # even after the command use to start it has been terminated
        if args.command and args.server:
            requests.delete(args.server+API+"shutdown")

        # Stop the local sever or the command used start a remote one
        if sys.platform == "win32":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGINT)
        proc.wait(PROCESS_STOP_TIMEOUT)
    # Give remote tasks longer to stop
    if args.command:
        time.sleep(1)


# Description : Creates a test file
# Parameters  : string name - file NameError
#               int size    - file size in KiB or None to default to 1024KiB
#               string char - character to use as data
# Returns     : None
def CreateFile(name, size=1024, char='.'):
    # 1K block of dataaaaTRANSFER_WAIT
    data = char * 1024

    with open(name, "w") as f:
        for _ in range(size):
            f.write(data)


# Description : Creates a test files and directories
# Parameters  : None
# Returns     : None
def CreateTestFiles():
    for adir in test_dirs:
        dirname = os.path.join(args.src_dir, adir)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)

    for file in test_files:
        filename = os.path.join(args.src_dir, file)
        if not os.path.isfile(filename):
            CreateFile(filename)


# Description : Polls remote file until changed,
#               checksums against local file
#               displays timings
# Parameters  : string localfile  - local file
# Returns     : True if updated and matching
def WaitAndCheckFile(localfile, remotefile, description):
    start_time = time.time()
    elapsed    = 0
    mtime_ns   = os.stat(localfile).st_mtime_ns

    # Wait until mtime update as only set on the last block
    while(os.stat(remotefile).st_mtime_ns != mtime_ns):
        time.sleep(0.001)
        elapsed = time.time() - start_time
        if elapsed > TRANSFER_WAIT:
            print("File has not been updated (%s)" % description)
            return False

    time.sleep(1) # ensure files are closed

    if not CompareFiles(remotefile, localfile):
        print("File does not match after update (%s)" % description)
        return False

    print("%s in %.3f seconds" % (description, elapsed))
    return True


# Description : Checks if two files are the same
# Parameters  : string file1 - first filename
#               string file2 - second filename
# Returns     : bool         - True if the same
def CompareFiles(file1, file2):
    return GetDigest(file1) ==  GetDigest(file2)


# Description : Checksums a file using SHA1
# Parameters  : string filename - the file to checksum
# Returns     : bytes           - sha1 digest of file
def GetDigest(filename):
    h = hashlib.sha1()
    with open(filename, 'rb') as f:
        while True:
            # Reading is buffered, so we can read smaller chunks.
            data = f.read(h.block_size)
            if not data:
                break
            h.update(data)
    return h.digest()



## Test Functions #############################################################

def Test1():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 1 ==========")
    print("Server started with no directory parameter creates the default Strorage directory")
    if args.command:
        print("SKIP: Can't run remote server without shared directory argument")
        return
    try:
        server_proc = StartServer(args.interface, None)
        if os.path.isdir(def_dest_dir):
            print("PASS: directory created")
            passed += 1
        else:
            print("FAIL: directory does not exist")
            failed += 1

        StopServer(server_proc)
        server_proc = None
        os.rmdir(def_dest_dir)
    except OSError as e:
        print("FAIL: Exception: %s" % str(e))
        failed += 1
    run += 1


def Test2():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 2 ==========")
    print("Server started with directory parameter creates the directory")
    try:
        server_proc = StartServer(args.interface, args.dest_dir)
        if os.path.isdir(args.dest_dir):
            print("PASS: directory created")
            passed += 1
        else:
            print("FAIL: directory does not exist")
            failed += 1
        StopServer(server_proc)
        server_proc = None
    except OSError as e:
        print("FAIL: Exception: %s" % str(e))
        failed += 1
    run += 1


def Test3():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 3 ==========")
    print("Client started with invalid directory fails")
    try:
        client_proc = StartClient(args.server, "dummy")
        time.sleep(1) # Wait for client
        if client_proc.poll() == 1:
            print("PASS: client exited")
            passed += 1
        else:
            print("FAIL: did not exit")
            failed += 1
            StopClient(client_proc)
            client_proc = None
    except OSError as e:
        print("FAIL: Exception: %s" % str(e))
        failed += 1
    run += 1


def Test4():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 4 ==========")
    print("Client with file and directories in source only")
    CreateTestFiles()

    try:
        if not server_proc:
            server_proc = StartServer(args.interface, args.dest_dir)

        client_proc = StartClient(args.server, args.src_dir)

        time.sleep(TRANSFER_WAIT)   # Wait for transfer

        ok = True

        # Check directories
        for adir in test_dirs:
            if not os.path.isdir(os.path.join(args.dest_dir, adir)):
                print("Directory not found in destination: %s" % adir)
                ok = False

        # Check file
        for file in test_files:
            if not os.path.isfile(os.path.join(args.dest_dir, file)):
                print("File not found in destination: %s" % file)
                ok = False

        if ok:
            print("PASS: all files copied")
            passed += 1
        else:
            print("FAIL: not all files and directories copied")
            failed += 1
    except OSError as e:
        print("FAIL: Exception: %s" % str(e))
        failed += 1
    run += 1


def Test5():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 5 ==========")
    print("Create new files and directories")
    try:
        new_files = [ "NewFile1", os.path.join("DirToRename", "NewFile2") ]
        new_dirs  = [ "NewDir1",  os.path.join("DirToRename", "NewDir2")  ]

        for file in new_files:
            CreateFile(os.path.join(args.src_dir, file))

        for adir in new_dirs:
            os.makedirs(os.path.join(args.src_dir, adir))

        time.sleep(TRANSFER_WAIT)

        ok = True

        # Check files
        for file in new_files:
            if not os.path.isfile(os.path.join(args.dest_dir, file)):
                print("File not found in destination: %s" % file)
                ok = False

        # Check directories
        for adir in new_dirs:
            if not os.path.isdir(os.path.join(args.dest_dir, adir)):
                print("FAIL: Directory not found in destination: %s" % adir)
                ok = False

        if ok:
            print("PASS: new files and directories copied")
            passed += 1
        else:
            print("FAIL: not all new directories copied")
            failed += 1

    except OSError as e:
        print("FAIL: Exception: %s" % str(e))
        failed += 1
    run += 1


def Test6():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 6 ==========")
    print("Delete files and directories")
    try:
        filetodelete = "FileToDelete"
        dirtodlete   = "DirToDelete"
        os.remove(os.path.join(args.src_dir, filetodelete))
        shutil.rmtree(os.path.join(args.src_dir, "DirToDelete"))

        time.sleep(TRANSFER_WAIT)

        if os.path.isfile(os.path.join(args.dest_dir, filetodelete)):
            print("FAIL: failed to remove file: %s" % filetodelete)
            failed += 1
        elif os.path.isdir(os.path.join(args.dest_dir, dirtodlete)):
            print("FAIL: failed to remove directory: %s" % dirtodlete)
            failed += 1
        else:
            print("PASS: files and directories deleted")
            passed += 1

    except OSError as e:
        print("FAIL: Exception: %s" % str(e))
        failed += 1
    run += 1


def Test7():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 7 ==========")
    print("Modify files")
    try:
        ok = True

        # Change first byte of file
        if ok:
            localfile  = os.path.join(args.src_dir,  "FileToChangeStart")
            remotefile = os.path.join(args.dest_dir, "FileToChangeStart")
            with open(localfile, "r+") as f:
                f.write('!')
            ok = WaitAndCheckFile(localfile, remotefile, "Change first byte")

        # Add 1 byte to end of file
        if ok:
            localfile  = os.path.join(args.src_dir,  "FileToAdd1")
            remotefile = os.path.join(args.dest_dir, "FileToAdd1")
            with open(localfile, "a") as f:
                f.write('!')
            ok = WaitAndCheckFile(localfile, remotefile, "Add 1 byte")

        # Remove 1 byte from end of file
        if ok:
            localfile  = os.path.join(args.src_dir,  "FileToRemove1")
            remotefile = os.path.join(args.dest_dir, "FileToRemove1")
            with open(localfile, "r+") as f:
                f.truncate(os.stat(localfile).st_size-1)
            ok = WaitAndCheckFile(localfile, remotefile, "Remove 1 byte")

        # Entirely new file
        if ok:
            localfile  = os.path.join(args.src_dir,  "FileToReplace")
            remotefile = os.path.join(args.dest_dir, "FileToReplace")
            CreateFile(localfile, char=":")
            ok = WaitAndCheckFile(localfile, remotefile, "All blocks changed")

        # Check that file updated again holds off for the update rate
        if ok:
            localfile  = os.path.join(args.src_dir,  "FileToReplace")
            remotefile = os.path.join(args.dest_dir, "FileToReplace")
            # update a byte in the middle for a change
            with open(localfile, "r+") as f:
                f.seek(os.stat(localfile).st_size/2)
                f.write('!')
            # check the file hasn't been updated before the inerval
            print("Waiting %d seconds for file update rate limiting..." % updatemax)
            time.sleep(updatemax-2)
            if CompareFiles(localfile, remotefile):
                print("Modified file updated before update max time")
                ok = False
            else:
                ok = WaitAndCheckFile(localfile, remotefile, "Updated again")

        if ok:
            print("PASS: files updated")
            passed +=1
        else:
            print("FAIL: files not updated")
            failed += 1

    except OSError as e:
        print("FAIL: Exception: %s" % str(e))
        failed += 1
    run += 1


def Test8():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 8 ==========")
    print("Rename files and directories")
    try:
        renames = \
        [
            ("FileToRename", "FileRenamed"),
            ("DirToRename",  "DirRenamed"),
        ]

        for oldname, newname in renames:
            os.rename(os.path.join(args.src_dir, oldname), os.path.join(args.src_dir, newname))

        time.sleep(TRANSFER_WAIT)

        ok = True

        for oldname, newname in renames:
            oldname = os.path.join(args.dest_dir, oldname)
            newname = os.path.join(args.dest_dir, newname)
            if os.path.isfile(oldname) or os.path.isdir(oldname):
                print("FAIL: old object sitll exists: %s" % oldname)
                ok = False
            if not os.path.isfile(newname) and not os.path.isdir(newname):
                print("FAIL: new object doesn't exists: %s" % oldname)
                ok = False

        if ok:
            print("PASS: files and directories renamed")
            passed +=1
        else:
            print("FAIL: file not directories not renamed")
            failed += 1

    except OSError as e:
        print("FAIL: Exception: %s" % str(e))
        failed += 1
    run += 1


## Main #######################################################################

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Directory Synchronisation Test")
    parser.add_argument("-t", "--test",         type=int,   default=0,          help="Test number to run, defaults to all tests")
    parser.add_argument("-s", "--server",                                       help="Server host:port")
    parser.add_argument("-i", "--interface",                                    help="Interface for server to bind to")
    parser.add_argument("-c", "--command",                                      help="Command to use when starting server, e.g. \"ssh hostname python3 path/server.py\"")
    parser.add_argument("-b", "--blocksize",                                    help="Block size for file change detection for server")
    parser.add_argument("-u", "--updatemax",                                    help="Only update a file once per interval for client")
    parser.add_argument("src_dir",              nargs='?',  default=src_dir,    help="directory to synchronise from, defaults to "+src_dir)
    parser.add_argument("dest_dir",             nargs='?',  default=dest_dir,   help="directory to synchronise to, defaults to "+dest_dir)
    args = parser.parse_args()

    if args.updatemax:
        updatemax = int(args.updatemax)

    # remove any existing source and destination directories
    if os.path.isdir(args.src_dir):
        shutil.rmtree(args.src_dir)

    if os.path.isdir(args.dest_dir):
        shutil.rmtree(args.dest_dir)

    if os.path.isdir(def_dest_dir):
        shutil.rmtree(def_dest_dir)

    # Run tests

    try:
        # Initial tests with no client or server running
        # and close client and server on exit
        if args.test==0 or args.test==1:
            Test1()

        if args.test==0 or args.test==2:
            Test2()

        if args.test==0 or args.test==3:
            Test3()

        if args.test==0 or args.test==4:
            Test4()

        # Client, server and test files required for subsequent tests,
        # and left running after each
        if args.test >= 5:
            CreateTestFiles()
            if not server_proc:
                server_proc = StartServer(args.interface, args.dest_dir)
            if not client_proc:
                client_proc = StartClient(args.server, args.src_dir)
                time.sleep(TRANSFER_WAIT)

        if args.test==0 or args.test==5:
            Test5()

        if args.test==0 or args.test==6:
            Test6()

        if args.test==0 or args.test==7:
            Test7()

        if args.test==0 or args.test==8:
            Test8()

    finally:
        # Stop any running programs
        StopClient(client_proc)
        StopServer(server_proc)

    print("========== Summary ==========")
    print("Run    : %d" % run)
    print("Passed : %d" % passed)
    print("Failed : %d" % failed)

    # return non zero if failures
    sys.exit(failed)


## EOF ########################################################################
