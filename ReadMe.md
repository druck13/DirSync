DirSync

Purpose

Simple synchronisation a local directory with a remote directory, in the style of drop box.

Installation
------------
Runs on both Linux. Requires Python 3.6 or later.

The following Python3 packages are required, and can be installed with python -m pip install <package>

* shutil
* json
* requests
* watcher
* flask

Running
-------

On the machine containing the directory to synchronise run

python3 client.py <directory>

On the machine to synchronsise to (which can be the same machine, or a remote machine*), run

python3 server.py [<directory>]

If directory is not supplied, it will default to Storage in the same directory.

* For security reasons the server only binds to the loopback network interface,
to it is only accessible to the local machine. To use set up an ssh tunnel for port 5000.

e.g. ssh <remotemachine> -L localhost:5000:localhost:5000

For use on the local network on a machine protected from the internet by a firewall and
external interface can be specified.

python3 server.py [<directory>] [-i <host:port>]

When running both client and server will display information on synchronisation to stdout.


Testing
-------

The program test.py will set up the client and server on a local Linux and Windows machines
and run a series of confidence tests

Test 1: Server started with no directory parameter creates the default Strorage directory
Test 2: Server started with directory parameter creates the directory
Test 3: Client started with invalid directory fails
Test 4: Client with file and directories in source only
Test 5: Create new files and directories
Test 6: Delete files and directories
Test 7: Modify a file
Test 8: Rename files and directories
