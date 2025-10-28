"""
xgdatatools - eXtreme Gammon binary file parser

Original author: Michael Petch <mpetch@gnubg.org>
License: LGPL-3.0 or later
Source: https://github.com/oysteijo/xgdatatools

This package contains the xgdatatools library for parsing eXtreme Gammon
binary (.xg) file formats.
"""

from . import xgimport
from . import xgstruct
from . import xgutils
from . import xgzarc

__all__ = ['xgimport', 'xgstruct', 'xgutils', 'xgzarc']
