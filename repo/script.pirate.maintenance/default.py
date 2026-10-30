#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys

import xbmc

from resources.lib.maintenance import run_manual


def get_action():
    for argument in sys.argv[1:]:
        if argument.lower().startswith("action="):
            return argument.split("=", 1)[1].lower()
    return "cleanup"


if get_action() == "cleanup":
    run_manual()
else:
    xbmc.log(
        "The Pirate Maintenance: unsupported action %s" % get_action(),
        xbmc.LOGWARNING,
    )
