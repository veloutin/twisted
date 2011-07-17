#!/usr/bin/env python
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Distutils installer for Twisted.
"""

import os, sys

if sys.version_info < (2,3):
    print >>sys.stderr, "You must use at least Python 2.3 for Twisted"
    sys.exit(3)

if os.path.exists('twisted'):
    sys.path.insert(0, '.') # eek! need this to import twisted. sorry.
from twisted import copyright
from twisted.python.dist import setup, ConditionalExtension as Extension
from twisted.python.dist import getPackages, getDataFiles, getScripts
from twisted.python.dist import twisted_subprojects

import platform


def _isCPython():
    try:
        return platform.python_implementation() == "CPython"
    except AttributeError:
        # For 2.5:
        try:
            implementation, _, _ = sys.subversion
            return implementation == "CPython"
        except AttributeError:
            pass

        # Pythons older than 2.5 require us to try and guess by
        # elimination. If you're on such an old, obscure version of
        # Python, I can't help you.
        
        # Are we on Pypy?
        if "__pypy__" in sys.modules:
            return False

        # Guess not. Are we on Jython?
        try:
            platform.java_ver 
            return False
        except AttributeError:
            pass

        # Guess not. Are we on IronPython?
        try:
            import clr
            return False
        except ImportError:
            pass
        
        # Well, then we're *probably* on CPython.
        return True


isCPython = _isCPython()


def hasEpoll(builder):
    builder._check_header("sys/epoll.h")


extensions = [
    Extension("twisted.test.raiser",
              ["twisted/test/raiser.c"],
              condition=lambda _: isCPython),

    Extension("twisted.python._epoll",
              ["twisted/python/_epoll.c"],
              condition=lambda builder: isCPython and hasEpoll(builder)),

    Extension("twisted.internet.iocpreactor.iocpsupport",
              ["twisted/internet/iocpreactor/iocpsupport/iocpsupport.c",
               "twisted/internet/iocpreactor/iocpsupport/winsock_pointers.c"],
              libraries=["ws2_32"],
              condition=lambda _: isCPython and sys.platform == "win32"),

    Extension("twisted.python._initgroups",
              ["twisted/python/_initgroups.c"]),
    Extension("twisted.internet._sigchld",
              ["twisted/internet/_sigchld.c"],
              condition=lambda _: sys.platform != "win32"),
]

# Figure out which plugins to include: all plugins except subproject ones
subProjectsPlugins = ['twisted_%s.py' % subProject
                      for subProject in twisted_subprojects]
plugins = os.listdir(os.path.join(
    os.path.dirname(os.path.abspath(copyright.__file__)), 'plugins'))
plugins = [plugin[:-3] for plugin in plugins if plugin.endswith('.py') and
           plugin not in subProjectsPlugins]



setup_args = dict(
    # metadata
    name="Twisted Core",
    version=copyright.version,
    description="The core parts of the Twisted networking framework",
    author="Twisted Matrix Laboratories",
    author_email="twisted-python@twistedmatrix.com",
    maintainer="Glyph Lefkowitz",
    url="http://twistedmatrix.com/",
    license="MIT",
    long_description="""\
This is the core of Twisted, including:
 * Networking support (twisted.internet)
 * Trial, the unit testing framework (twisted.trial)
 * AMP, the Asynchronous Messaging Protocol (twisted.protocols.amp)
 * Twisted Spread, a remote object system (twisted.spread)
 * Utility code (twisted.python)
 * Basic abstractions that multiple subprojects use
   (twisted.cred, twisted.application, twisted.plugin)
 * Database connectivity support (twisted.enterprise)
 * A few basic protocols and protocol abstractions (twisted.protocols)
""",

    # build stuff
    packages=getPackages('twisted',
                         ignore=twisted_subprojects + ['plugins']),
    plugins=plugins,
    data_files=getDataFiles('twisted', ignore=twisted_subprojects),
    conditionalExtensions=extensions,
    scripts = getScripts(""),
)


if __name__ == '__main__':
    setup(**setup_args)
