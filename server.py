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

## Constants ##################################################################

## Global Variables ###########################################################

interface = "localhost:5000"    # Address:port to bind server to
directory = "Storage"           # Name of directory to synchronise to

## Classes ####################################################################

## Functions ##################################################################

## Main #######################################################################

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Directory Synchronisation Server")
    parser.add_argument("-i", "--interface",        default=interface,  help="Interface to bind to, defaults to "+interface)
    parser.add_argument("directory",    nargs='?',  default=directory,  help="directory to synchronise")
    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print("Server: Creating directory: %s" % args.directory)
        os.makedirs(args.directory)

    try:
        while True:
           time.sleep(1)
    except KeyboardInterrupt:
        print("Server: Terminated by the user")

## EOF ########################################################################
