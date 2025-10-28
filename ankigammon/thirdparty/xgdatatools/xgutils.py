#
#   xgutils.py - XG related utility functions
#   Copyright (C) 2013  Michael Petch <mpetch@gnubg.org>
#                                     <mpetch@capp-sysware.com>
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Lesser General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Lesser General Public License for more details.
#
#   You should have received a copy of the GNU Lesser General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#

import sys as _sys
import zlib as _zlib
import datetime as _datetime


def streamcrc32(stream, numbytes=None, startpos=None, blksize=32768):
    """Compute the CRC32 on a given stream. Restore the original
    position in the stream upon finishing. Process the stream in
    chunks defined by blksize
    """

    crc32 = 0
    curstreampos = stream.tell()

    if startpos is not None:
        stream.seek(startpos, 0)

    if numbytes is None:
        block = stream.read(blksize)
        while len(block) > 0:
            crc32 = _zlib.crc32(block, crc32)
            block = stream.read(blksize)
    else:
        bytesleft = numbytes
        while True:
            if bytesleft < blksize:
                blksize = bytesleft

            block = stream.read(blksize)
            crc32 = _zlib.crc32(block, crc32)
            bytesleft = bytesleft - blksize

            if bytesleft == 0:
                break

    stream.seek(curstreampos)
    return crc32 & 0xffffffff


def utf16intarraytostr3x(intarray):
    """Python 3.x - Convert an array of integers (UTF16) to a
    string. Input array is null terminated.
    """
    newstr = []
    for intval in intarray:
        if intval == 0:
            break
        newstr += [chr(intval).encode('utf-8')]

    return (b''.join([x for x in newstr]))


def utf16intarraytostr2x(intarray):
    """Python 2.x - Convert an array of integers (UTF16) to a
    string. Input array is null terminated.
    """
    newstr = []
    for intval in intarray:
        if intval == 0:
            break
        newstr += [unichr(intval).encode('utf-8')]

    return ''.join(newstr)

def delphidatetimeconv(delphi_datetime):
    """Convert a double float Delphi style timedate object to a Python
    datetime object. Delphi uses the number of days since
    Dec 30th, 1899 in the whole number component. The fractional
    component represents the fraction of a day (multiply by 86400
    to translate to seconds)
    """

    delta = _datetime.timedelta(
        days=int(delphi_datetime),
        seconds=int(86400 * (delphi_datetime % 1)))
    return _datetime.datetime(1899, 12, 30) + delta


def delphishortstrtostr(shortstring_abytes):
    """Convert Delphi Pascal style shortstring to a Python string.
    shortstring is a single byte (length of string) followed by
    length number of bytes. shortstrings are not null terminated.
    """

    return ''.join([chr(char) for char in
                    shortstring_abytes[1:(shortstring_abytes[0] + 1)]])


if __name__ == '__main__':
    pass
else:
    # Map the utf16intarraytostr function depending on whether
    # we are using Python 3.x or 2.x
    if _sys.version_info >= (3, 0):
        utf16intarraytostr = utf16intarraytostr3x
    else:
        utf16intarraytostr = utf16intarraytostr2x

