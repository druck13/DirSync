#!/usr/bin/env python3
###############################################################################
## Directory Synchronization Test Suite
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

SERVERSTART_WAIT        = 2             # Time to wait for server to start
REMOTE_STOP_WAIT        = 2             # Time to wait for a remote server to stop
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


def start_client(hostport, srcdir):
    """
    Runs the client program
    :param hostport: server address and port, or None
    :type hostport: string
    :param srcdir: source directory or None
    :type srcdir: string
    :return: process structure
    :rtype: class Popen
    """
    command = [ "python3", "client.py" ]

    if hostport:
        command += [ "--server", hostport ]

    if args.updatemax:
        command += [ "--updatemax", args.updatemax ]

    if srcdir:
        command.append(srcdir)

    print("Starting %s" % " ".join(command))
    return subprocess.Popen(command)


def stop_client(proc):
    """
    Stops the client by sending Ctrl+C and waits
    raises subprocess.timeoutexpired if process fails to stop
    :param proc: process structure of program
    :type proc:
    """
    if proc is not None:
        if sys.platform == "win32":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGINT)
        proc.wait(PROCESS_STOP_TIMEOUT)


def start_server(hostport, dstdir):
    """
    Runs the server program
    :param hostport: server interface or None
    :type hostport: string
    :param dstdir: destination directory or None
    :type dstdir: string or None
    :return: process structure
    :rtype: class Popen
    """
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
    # pylint: disable=consider-using-with
    ret = subprocess.Popen(command)
    # pylint: enable=consider-using-with

    # Wait for server to start before starting client
    time.sleep(SERVERSTART_WAIT)

    return ret

def stop_server(proc):
    """
    Stops the server sending a Ctrl+C if running locally
    or using the shutdown APU for a remote server
    raises subprocess.timeoutexpired if process fails to stop
    :param proc: subprocess.Popen
    :type proc: subprocess
    """
    if proc is not None:
        # shutdown a remote server, otherwise will remain running
        # even after the command use to start it has been terminated
        if args.command and args.server:
            print("Stopping remote server http://"+args.server+API+"shutdown")
            requests.post("http://"+args.server+API+"shutdown")

        # Stop the local sever or the command used start a remote one
        if sys.platform == "win32":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGINT)
        proc.wait(PROCESS_STOP_TIMEOUT)

        # Give remote tasks longer to stop
        if args.command:
            time.sleep(REMOTE_STOP_WAIT)


def create_file(name, size=1024, char='.'):
    """
    Creates a test file
    :param name: filename
    :type name: string
    :param size: file size in KiB or None to default to 1024KiB
    :type size: int
    :param char: character to use as data
    :type char: string
    """
    # 1K block of data
    data = char * 1024

    with open(name, "w", encoding="utf-8") as f:
        for _ in range(size):
            f.write(data)


def create_test_files():
    """
    Creates a test files and directories
    """
    for adir in test_dirs:
        dirname = os.path.join(args.src_dir, adir)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)

    for file in test_files:
        filename = os.path.join(args.src_dir, file)
        if not os.path.isfile(filename):
            create_file(filename)


def wait_and_check_file(localfile, remotefile, description):
    """
    Polls remote file until changed, checksums against local file, displays timings
    :param localfile: local filename
    :type localfile: string
    :param remotefile: remote filename
    :type remotefile: string
    :param description: description to print on failure
    :type description: string
    :return: True if updated and matching
    :rtype: bool
    """
    start_time = time.time()
    elapsed    = 0
    mtime_ns   = os.stat(localfile).st_mtime_ns

    # Wait until mtime update as only set on the last block
    while os.stat(remotefile).st_mtime_ns != mtime_ns:
        time.sleep(0.001)
        elapsed = time.time() - start_time
        if elapsed > TRANSFER_WAIT:
            print("File has not been updated (%s)" % description)
            return False

    time.sleep(1) # ensure files are closed

    if not compare_files(remotefile, localfile):
        print("File does not match after update (%s)" % description)
        return False

    print("%s in %.3f seconds" % (description, elapsed))
    return True


def compare_files(file1, file2):
    """
    Checks if two files are the same
    :param file1: first filename
    :type file1: string
    :param file2: second filename
    :type file2: string
    :return: True if the same
    :rtype: bool
    """
    return get_digest(file1) == get_digest(file2)


def get_digest(filename):
    """
    Checksums a file using SHA1
    :param filename: the file to checksum
    :type filename: string
    :return: sha1 digest of file
    :rtype: bytes
    """
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

def test1():
    global server_proc, run, passed, failed
    print("========== Test 1 ==========")
    print("Server started with no directory parameter creates the default Strorage directory")
    if args.command:
        print("SKIP: Can't run remote server without shared directory argument")
        return
    try:
        server_proc = start_server(args.interface, None)
        if os.path.isdir(def_dest_dir):
            print("PASS: directory created")
            passed += 1
        else:
            print("FAIL: directory does not exist")
            failed += 1

        stop_server(server_proc)
        server_proc = None
        os.rmdir(def_dest_dir)
    except OSError as e:
        print("FAIL: Exception: %s" % str(e))
        failed += 1
    run += 1


def test2():
    global server_proc, run, passed, failed
    print("========== Test 2 ==========")
    print("Server started with directory parameter creates the directory")
    try:
        server_proc = start_server(args.interface, args.dest_dir)
        time.sleep(1) # Wait for server
        if os.path.isdir(args.dest_dir):
            print("PASS: directory created")
            passed += 1
        else:
            print("FAIL: directory does not exist")
            failed += 1
        stop_server(server_proc)
        server_proc = None
    except OSError as e:
        print("FAIL: Exception: %s" % str(e))
        failed += 1
    run += 1


def test3():
    global client_proc, run, passed, failed
    print("========== Test 3 ==========")
    print("Client started with invalid directory fails")
    try:
        client_proc = start_client(args.server, "dummy")
        time.sleep(1) # Wait for client
        if client_proc.poll() == 1:
            print("PASS: client exited")
            passed += 1
        else:
            print("FAIL: did not exit")
            failed += 1
            stop_client(client_proc)
            client_proc = None
    except OSError as e:
        print("FAIL: Exception: %s" % str(e))
        failed += 1
    run += 1


def test4():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 4 ==========")
    print("Client with file and directories in source only")
    create_test_files()

    try:
        if not server_proc:
            server_proc = start_server(args.interface, args.dest_dir)

        client_proc = start_client(args.server, args.src_dir)

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


def test5():
    global run, passed, failed
    print("========== Test 5 ==========")
    print("Create new files and directories")
    try:
        new_files = [ "NewFile1", os.path.join("DirToRename", "NewFile2") ]
        new_dirs  = [ "NewDir1",  os.path.join("DirToRename", "NewDir2")  ]

        for file in new_files:
            create_file(os.path.join(args.src_dir, file))

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


def test6():
    global run, passed, failed
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


def test7():
    global run, passed, failed
    print("========== Test 7 ==========")
    print("Modify files")
    try:
        ok = True

        # Change first byte of file
        if ok:
            localfile  = os.path.join(args.src_dir,  "FileToChangeStart")
            remotefile = os.path.join(args.dest_dir, "FileToChangeStart")
            with open(localfile, "r+", encoding="utf-8") as f:
                f.write('!')
            ok = wait_and_check_file(localfile, remotefile, "Change first byte")

        # Add 1 byte to end of file
        if ok:
            localfile  = os.path.join(args.src_dir,  "FileToAdd1")
            remotefile = os.path.join(args.dest_dir, "FileToAdd1")
            with open(localfile, "a", encoding="utf-8") as f:
                f.write('!')
            ok = wait_and_check_file(localfile, remotefile, "Add 1 byte")

        # Remove 1 byte from end of file
        if ok:
            localfile  = os.path.join(args.src_dir,  "FileToRemove1")
            remotefile = os.path.join(args.dest_dir, "FileToRemove1")
            with open(localfile, "r+", encoding="utf-8") as f:
                f.truncate(os.stat(localfile).st_size-1)
            ok = wait_and_check_file(localfile, remotefile, "Remove 1 byte")

        # Entirely new file
        if ok:
            localfile  = os.path.join(args.src_dir,  "FileToReplace")
            remotefile = os.path.join(args.dest_dir, "FileToReplace")
            create_file(localfile, char=":")
            ok = wait_and_check_file(localfile, remotefile, "All blocks changed")

        # Check that file updated again holds off for the update rate
        if ok:
            localfile  = os.path.join(args.src_dir,  "FileToReplace")
            remotefile = os.path.join(args.dest_dir, "FileToReplace")
            # update a byte in the middle for a change
            with open(localfile, "r+", encoding="utf-8") as f:
                f.seek(os.stat(localfile).st_size//2)
                f.write('!')
            # check the file hasn't been updated before the inerval
            print("Waiting %d seconds for file update rate limiting..." % updatemax)
            time.sleep(TRANSFER_WAIT)
            if compare_files(localfile, remotefile):
                print("Modified file updated before update max time")
                ok = False
            else:
                time.sleep(updatemax-TRANSFER_WAIT)
                ok = wait_and_check_file(localfile, remotefile, "Updated again")

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


def test8():
    global run, passed, failed
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
    parser.add_argument("-c", "--command",                                      help="Command to use when starting server," \
                                                                                     "e.g. \"ssh hostname python3 path/server.py\"")
    parser.add_argument("-b", "--blocksize",                                    help="Block size for file change detection for server")
    parser.add_argument("-u", "--updatemax",                                    help="Only update a file once per interval for client")
    parser.add_argument("src_dir",              nargs='?',  default=src_dir,    help="directory to synchronise from, defaults to "+src_dir)
    parser.add_argument("dest_dir",             nargs='?',  default=dest_dir,   help="directory to synchronise to, defaults to "+dest_dir)
    args = parser.parse_args()

    if args.updatemax:
        updatemax = int(args.updatemax)

    if args.command:
        TRANSFER_WAIT *= 3  # increase time for transfers with a remote sever

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
        if args.test in (0, 1):
            test1()

        if args.test in (0, 2):
            test2()

        if args.test in (0, 3):
            test3()

        if args.test in (0, 4):
            test4()

        # Client, server and test files required for subsequent tests,
        # and left running after each
        if args.test >= 5:
            create_test_files()
            if not server_proc:
                server_proc = start_server(args.interface, args.dest_dir)
            if not client_proc:
                client_proc = start_client(args.server, args.src_dir)
                time.sleep(TRANSFER_WAIT)

        if args.test in (0, 5):
            test5()

        if args.test in (0, 6):
            test6()

        if args.test in (0, 7):
            test7()

        if args.test in (0, 8):
            test8()

    finally:
        # Stop any running programs
        stop_client(client_proc)
        stop_server(server_proc)

    print("========== Summary ==========")
    print("Run    : %d" % run)
    print("Passed : %d" % passed)
    print("Failed : %d" % failed)

    # return non zero if failures
    sys.exit(failed)


## EOF ########################################################################
