DirSync v1.0
============

Purpose
-------
Simple synchronisation a local directory with a remote directory, in the style of drop box.


Installation
------------
Runs on both Linux. Requires Python 3.6 or later.

The following Python3 packages are required, and can be installed with python -m pip install &lt;package&gt;

* requests
* watcher
* flask


Running
-------
*  On the machine to synchronise to (which can be the same machine, or a remote machine*), run

python3 server.py [&lt;directory&gt;]

If directory is not supplied, it will default to Storage in the same directory.

* For security reasons the server only binds to the loopback network interface,
to it is only accessible to the local machine. To use set up an ssh tunnel for port 5000.

For use on the local network on a machine protected from the internet by a firewall and
external interface can be specified.

python3 server.py [&lt;directory&gt; ] [-i &lt;host:port&gt;]

e.g. ssh &lt;remotemachine&gt; -L localhost:5000:localhost:5000

* On the machine containing the directory to synchronise run

python3 client.py &lt;directory&gt;

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
* Test 7: Modify a file
* Test 8: Rename files and directories



Future Versions
---------------
* v1.1: Files are loaded in to memory for synchronisation which will fail for massive files,
and will be slow. The new version will handle files in chunks, and will only copy those
chunks which changed

* v1.2: Files are synchronised as soon as they are changed which will lead to a lot of bandwidth
use for frequently changed files. A queuing system will be implemented to limit copying to
once per 60 seconds, or a configurable interval


ToDo
----
* Functionality - Implement file permissions and ownership
* Robustness    - Any errors kill the client or server, these need to be handled
                  better. The client needs to be able to wait for the server to
                  respawn, and filing system errors need to be handled sensibly
* Testing       - Only a limited amount of testing on Linux and Windows
                  No testing betweem client and server on different OS's
* Security      - No authentication used in the flask protocol
