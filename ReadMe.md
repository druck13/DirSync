DirSync v1.2
============

Purpose
-------
Simple synchronisation of a local directory with a remote directory, in the style of drop box.


Installation
------------
Runs on both Linux. Requires Python 3.6 or later.

The following Python3 packages are required, and can be installed with python -m pip install &lt;package&gt;

* requests
* watcher
* flask


Running
-------
On the machine to synchronise to (which can be the same machine, or a remote machine*), run

    python3 server.py [<directory>]

If directory is not supplied, it will default to Storage in the same directory.

For security reasons the server only binds to the loopback network interface,
to it is only accessible to the local machine. To use set up an ssh tunnel for port 5000.

For use on the local network on a machine protected from the internet by a firewall and
external interface can be specified.

    python3 server.py [<directory>] [-i <host:port>]

e.g.

    ssh <remotemachine> -L localhost:5000:localhost:5000

On the machine containing the directory to synchronise run

    python3 client.py <directory>;

When running both client and server will display information on synchronisation to stdout.


Testing
-------
The program test.py will by default set up the client and server on a local Linux and Windows
machines and run a series of confidence tests.

* Test 1: Server started with no directory parameter creates the default Storage directory
* Test 2: Server started with directory parameter creates the directory
* Test 3: Client started with invalid directory fails
* Test 4: Client with file and directories in source only
* Test 5: Create new files and directories
* Test 6: Delete files and directories
* Test 7: Modify files
* Test 8: Rename files and directories

Tests can be run with the server on a remote machine if it can be started via a command such as ssh,
and a shared directory is avialble on both machines with the same path

e.g.

    python3 test.py --server MyServer:5000 -interface 0.0.0.0:5000 --command "ssh MyServer python3 PythonPrograms/DirSync/server.py" Source /mnt/SharedDisc/Destination

Note: Some tests may fail with high latency and/or low bandwidth networks, due to fixed waits for transfers.


History
-------
* Version 1.0
  * Initial release
* Version 1.1
  * Only changed parts of files are copied
  * Client waits for server to start
* Version 1.2
  * Rate limits file updating to a configurable interval


ToDo
----
* Functionality - Implement file permissions and ownership
* Robustness    - Any errors kill the client or server, these need to be handled
                  better. The client needs to be able to wait for the server to
                  respawn, and filing system errors need to be handled sensibly
* Testing       - Only a limited amount of testing on Linux and Windows
                  No testing betweem client and server on different OS's
* Security      - No authentication used in the flask protocol, use https to
                  hide data from third parties
