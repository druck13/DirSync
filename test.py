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

## Constants ##################################################################

SERVERSTART_WAIT        = 1             # Time to wait for server to start
TRANSFER_WAIT           = 5             # Time to wait for data transfers
PROCESS_STOP_TIMEOUT    = 10            # Time to wait for program to stop

## Global Variables ###########################################################

# Argument defaults
server          = "localhost:5000"      # host:port of server
interface       = "localhost:5000"      # Interface for sever to bind to
src_dir         = "Source"              # Name of directory to synchronise from
dest_dir        = "Destination"         # Name of directory to synchronise to
def_dest_dir    = "Storage"             # Default directory used by server

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
    "ExistingDir1",
    "ExistingDir2"
]
test_files = \
[
    "ExistingFile1",
    "ExistingFile2",
    "ExistingFile3",
    "ExistingFile4",
    os.path.join("ExistingDir1", "ExistingFile4"),
    os.path.join("ExistingDir1", "ExistingFile5"),
]

## Functions ##################################################################


# Description : Runs the client program
# Parameters  : string addrport - server address and port, or None
#             : string srcdir   - source directory or None
# Returns     : class Popen     - process structure
def StartClient(addrport, srcdir):
    command = [ "python3", "client.py" ]

    if addrport:
        command += [ "--server", addrport ]

    if srcdir:
        command.append(srcdir)

    print("Starting %s" % " ".join(command))
    return subprocess.Popen(command)


# Description : Runs the server program
# Parameters  : string addrport - server interface or None
#             : string dstdir   - destination directory or None
# Returns     : class Popen     - process structure
def StartServer(addrport, dstdir):
    command = [ "python3", "server.py" ]

    if addrport:
        command += [ "--interface", addrport ]

    if dstdir:
        command.append(dstdir)

    print("Starting %s" % " ".join(command))
    ret = subprocess.Popen(command)

    # Wait for server to start before starting client
    time.sleep(SERVERSTART_WAIT);

    return ret


# Description : Stops running programs by sending Ctrl+C and waits
# Parameters  : subprocess proc - process structure of program
# Returns     : None
# Exceptions  : subprocess.timeoutexpired if process fails to stop
def StopProgram(proc):
    if proc is not None:
        if sys.platform == "win32":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGINT)
        proc.wait(PROCESS_STOP_TIMEOUT)


# Description : Creates a test file
# Parameters  : string name - file NameError
#               size        - file size in KiB or None to default to 1024KiB
# Returns     : None
def CreateFile(name, size=1024):
    # 1K block of dataaaaTRANSFER_WAIT
    data = "." * 1024

    with open(name, "w") as f:
        for i in range(size):
            f.write(data)


# Description : Creates a test files and directories
# Parameters  : None
# Returns     : None
def CreateTestFiles():
    for dir in test_dirs:
        dirname = os.path.join(args.src_dir, dir)
        if not os.path.isdir(dirname):
            os.makedirs(dirname)

    for file in test_files:
        filename = os.path.join(args.src_dir, file)
        if not os.path.isfile(filename):
            CreateFile(filename)


# Description : checks if two files are the same
# Parameters  : string file1 - first file
# Returns     : string file2 - second file
def IsFileSame(file1, file2):
    stat1 = os.stat(file1)
    stat2 = os.stat(file2)

    # check file size and modification times match
    return stat1.st_size  == stat2.st_size and \
           stat2.st_mtime == stat2.st_mtime


## Test Functions #############################################################

def Test1():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 1 ==========")
    print("Server started with no directory parameter creates the default Strorage directory")
    try:
        server_proc = StartServer(None, None)
        if os.path.isdir(def_dest_dir):
            print("PASS: directory created")
            passed += 1
        else:
            print("FAIL: directory does not exist")
            failed += 1

        StopProgram(server_proc)
        server_proc = None
        os.rmdir(def_dest_dir)
    except OSError as e:
        print("FAIL: Exception %s" % str(e))
        failed += 1
    run += 1


def Test2():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 2 ==========")
    print("Server started with directory parameter creates the directory")
    try:
        server_proc = StartServer(None, args.dest_dir)
        if os.path.isdir(args.dest_dir):
            print("PASS: directory created")
            passed += 1
        else:
            print("FAIL: directory does not exist")
            failed += 1
        StopProgram(server_proc)
        server_proc = None
    except OSError as e:
        print("FAIL: Exception %s" % str(e))
        failed += 1
    run += 1


def Test3():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 3 ==========")
    print("Client started with invalid directory fails")
    try:
        client_proc = StartClient(None, "dummy")
        time.sleep(1) # Wait for client
        if client_proc.poll() == 1:
            print("PASS: directory created")
            passed += 1
        else:
            print("FAIL: did not exit")
            failed += 1
            StopProgram(server_proc)
            server_proc = None
    except OSError as e:
        print("FAIL: Exception %s" % str(e))
        failed += 1
    run += 1


def Test4():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 4 ==========")
    print("Client with file and directories in source only")
    CreateTestFiles()

    try:
        if not server_proc:
            server_proc = StartServer(None, args.dest_dir)

        client_proc = StartClient(None, args.src_dir)

        time.sleep(TRANSFER_WAIT)   # Wait for transfer

        ok = True

        # Check directories
        for dir in test_dirs:
            if not os.path.isdir(os.path.join(args.dest_dir, dir)):
                print("Directory not found in destination: %s" % dir)
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
        print("FAIL: Exception %s" % str(e))
        failed += 1
    run += 1


def Test5():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 5 ==========")
    print("Create new files and directories")
    try:
        new_files = [ "NewFile1", os.path.join("ExistingDir1", "NewFile2") ]
        new_dirs  = [ "NewDir1",  os.path.join("ExistingDir1", "NewDir2") ]

        for file in new_files:
            CreateFile(os.path.join(args.src_dir, file))

        for dir in new_dirs:
            os.makedirs(os.path.join(args.src_dir, dir))

        time.sleep(TRANSFER_WAIT)

        ok = True

        # Check files
        for file in new_files:
            if not os.path.isfile(os.path.join(args.dest_dir, file)):
                print("File not found in destination: %s" % file)
                ok = False

        # Check directories
        for dir in new_dirs:
            if not os.path.isdir(os.path.join(args.dest_dir, dir)):
                print("FAIL: Directory not found in destination: %s" % dir)
                ok = False

        if ok:
            print("PASS: new files and directories copied")
            passed += 1
        else:
            print("FAIL: not all new directories copied")
            failed += 1

    except OSError as e:
        print("FAIL: Exception %s" % str(e))
        failed += 1
    run += 1


def Test6():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 6 ==========")
    print("Delete files and directories")
    try:
        os.remove(os.path.join(args.src_dir, test_files[0]))
        shutil.rmtree(os.path.join(args.src_dir, test_dirs[0]))

        time.sleep(TRANSFER_WAIT)

        if os.path.isfile(os.path.join(args.dest_dir, test_files[0])):
            print("FAIL: failed to remove file: %s" % test_files[0])
            failed += 1
        elif os.path.isdir(os.path.join(args.dest_dir, test_dirs[0])):
            print("FAIL: failed to remove directory: %s" % test_dirs[0])
            failed += 1
        else:
            print("PASS: files and directories deleted")
            passed += 1

    except OSError as e:
        print("FAIL: Exception %s" % str(e))
        failed += 1
    run += 1


def Test7():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 7 ==========")
    print("Modify a file")
    try:
        # touch the file to change modification time
        localfile  = os.path.join(args.src_dir,  test_files[1])
        remotefile = os.path.join(args.dest_dir, test_files[1])
        os.utime(localfile, None)

        time.sleep(TRANSFER_WAIT)

        if IsFileSame(localfile, remotefile):
            print("PASS: file updated: %s" % test_files[1])
            passed +=1
        else:
            print("FAIL: file not updated: %s" % test_files[1])
            failed += 1

    except OSError as e:
        print("FAIL: Exception %s" % str(e))
        failed += 1
    run += 1


def Test8():
    global client_proc, server_proc, run, passed, failed
    print("========== Test 8 ==========")
    print("Rename files and directories")
    try:
        # touch the file to change modification time
        renames = \
        [
            (test_files[2], "RenamedFile1"),
            (test_dirs[1],  "RenamedDir1"),
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
        print("FAIL: Exception %s" % str(e))
        failed += 1
    run += 1


## Main #######################################################################

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Directory Synchronisation Test")
    parser.add_argument("-t", "--test", type=int,   default=0,          help="Test number to run, defaults to all tests")
    parser.add_argument("-s", "--server",           default=server,     help="Server host:port, defaults to "+server)
    parser.add_argument("-i", "--interface",        default=interface,  help="Interface to bind to, defaults to "+interface)
    parser.add_argument("src_dir",      nargs='?',  default=src_dir,    help="directory to synchronise from, defaults to "+src_dir)
    parser.add_argument("dest_dir",     nargs='?',  default=dest_dir,   help="directory to synchronise to, defaults to "+dest_dir)
    args = parser.parse_args()

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

        # Client an server and test files required for subsequent tests
        if args.test >= 5:
            CreateTestFiles()
            if not server_proc:
                server_proc = StartServer(None, args.dest_dir)
            if not client_proc:
                client_proc = StartClient(None, args.src_dir)
                time.sleep(2)

        if args.test==0 or args.test==5:
            # Test 4 needs to be run first
            if args.test==5:
                Test4()
            Test5()

        if args.test==0 or args.test==6:
            Test6()

        if args.test==0 or args.test==7:
            Test7()

        if args.test==0 or args.test==8:
            Test8()

    finally:
        # Stop any running programs
        StopProgram(client_proc)
        StopProgram(server_proc)

    print("========== Summary ==========")
    print("Run    : %d" % run)
    print("Passed : %d" % passed)
    print("Failed : %d" % failed)

    # return non zero if failures
    sys.exit(failed)


## EOF ########################################################################
