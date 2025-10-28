#
#   xgzarc.py - XG ZLib archive module
#   Copyright (C) 2013,2014  Michael Petch <mpetch@gnubg.org>
#                                          <mpetch@capp-sysware.com>
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
#   This library is an interpretation of ZLBArchive 1.52 data structures.
#   Please see: http://www.delphipages.com/comp/zlibarchive-2104.html
#

from __future__ import with_statement as _with
import tempfile as _tempfile
import struct as _struct
import zlib as _zlib
import os as _os
from . import xgutils as _xgutils


class Error(Exception):

    def __init__(self, error):
        self.value = "Zlib archive: %s" % str(error)
        self.error = error

    def __str__(self):
        return repr(self.value)


class ArchiveRecord(dict):

    SIZEOFREC = 36

    def __init__(self, **kw):
        defaults = {
            'crc': 0,
            'filecount': 0,
            'version': 0,
            'registrysize': 0,
            'archivesize': 0,
            'compressedregistry': False,
            'reserved': []
            }
        super(ArchiveRecord, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
        return self[key]

    def fromstream(self, stream):
        unpacked_data = _struct.unpack('<llllll12B',
                                       stream.read(self.SIZEOFREC))
        self.crc = unpacked_data[0] & 0xffffffff
        self.filecount = unpacked_data[1]
        self.version = unpacked_data[2]
        self.registrysize = unpacked_data[3]
        self.archivesize = unpacked_data[4]
        self.compressedregistry = bool(unpacked_data[5])
        self.reserved = unpacked_data[6:]


class FileRecord(dict):

    SIZEOFREC = 532

    def __init__(self, **kw):
        defaults = {
            'name': None,
            'path': None,
            'osize': 0,
            'csize': 0,
            'start': 0,
            'crc': 0,
            'compressed': False,
            'stored': False,
            'compressionlevel': 0
            }
        super(FileRecord, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
        return self[key]

    def fromstream(self, stream):
        unpacked_data = _struct.unpack('<256B256BllllBBxx',
                                       stream.read(self.SIZEOFREC))
        self.name = _xgutils.delphishortstrtostr(unpacked_data[0:256])
        self.path = _xgutils.delphishortstrtostr(unpacked_data[256:512])
        self.osize = unpacked_data[512]
        self.csize = unpacked_data[513]
        self.start = unpacked_data[514]
        self.crc = unpacked_data[515] & 0xffffffff
        self.compressed = bool(unpacked_data[516] == 0)
        self.compressionlevel = unpacked_data[517]

    def __str__(self):
        return str(self.todict())


class ZlibArchive(object):
    __MAXBUFSIZE = 32768
    __TMP_PREFIX = 'tmpXGI'

    def __init__(self, stream=None, filename=None):
        self.arcrec = ArchiveRecord()
        self.arcregistry = []
        self.startofarcdata = -1
        self.endofarcdata = -1

        self.filename = filename
        self.stream = stream
        if stream is None:
            self.stream = open(filename, 'rb')

        self.__getarchiveindex()

    def __extractsegment(self, iscompressed=True, numbytes=None):
        # Extract a stored segment
        filename = None
        stream = []

        try:
            tmpfd, filename = _tempfile.mkstemp(prefix=self.__TMP_PREFIX)
            with _os.fdopen(tmpfd, "wb") as tmpfile:

                if (iscompressed):
                    # Extract a compressed segment
                    decomp = _zlib.decompressobj()
                    buf = self.stream.read(self.__MAXBUFSIZE)
                    stream = decomp.decompress(buf)

                    if len(stream) <= 0:
                        raise IOError()

                    tmpfile.write(stream)

                    # Read until we have uncompressed a complete segment
                    while len(decomp.unused_data) == 0:
                        block = self.stream.read(self.__MAXBUFSIZE)
                        if len(block) > 0:
                            try:
                                stream = decomp.decompress(block)
                                tmpfile.write(stream)
                            except:
                                break
                        else:
                            # EOF reached
                            break

                else:
                    # Extract an uncompressed segment
                    # Uncompressed segment needs numbytes specified
                    if numbytes is None:
                        raise IOError()

                    blksize = self.__MAXBUFSIZE
                    bytesleft = numbytes
                    while True:
                        if bytesleft < blksize:
                            blksize = bytesleft

                        block = self.stream.read(blksize)
                        tmpfile.write(block)
                        bytesleft = bytesleft - blksize

                        if bytesleft == 0:
                            break

        except (_zlib.error, IOError) as e:
            _os.unlink(filename)
            return None

        return filename

    def __getarchiveindex(self):

        try:
            # Advance to the archive record at the end and retrieve it
            filerecords = []
            curstreampos = self.stream.tell()

            self.stream.seek(-ArchiveRecord.SIZEOFREC, _os.SEEK_END)
            self.endofarcdata = self.stream.tell()
            self.arcrec.fromstream(self.stream)

            # Position ourselves at the beginning of the archive file index
            self.stream.seek(-ArchiveRecord.SIZEOFREC -
                             self.arcrec.registrysize, _os.SEEK_END)
            self.startofarcdata = self.stream.tell() - self.arcrec.archivesize

            # Compute the CRC32 of all the archive data including file index
            streamcrc = _xgutils.streamcrc32(
                    self.stream,
                    startpos=self.startofarcdata,
                    numbytes=(self.endofarcdata - self.startofarcdata))
            if streamcrc != self.arcrec.crc:
                raise Error("Archive CRC check failed - file corrupt")

            # Decompress the index into a temporary file
            idx_filename = self.__extractsegment(
                    iscompressed=self.arcrec.compressedregistry)
            if idx_filename is None:
                raise Error("Error extracting archive index")

            # Retrieve all the files in the index
            with open(idx_filename, "rb") as idx_file:
                for recordnum in range(0, self.arcrec.filecount):
                    curidxpos = self.stream.tell()

                    # Retrieve next file index record
                    filerec = FileRecord()
                    filerec.fromstream(idx_file)
                    filerecords.append(filerec)

                    self.stream.seek(curidxpos, 0)

            _os.unlink(idx_filename)
        finally:
            self.stream.seek(curstreampos, 0)

        self.arcregistry = filerecords

    def getarchivefile(self, filerec):
        # Do processing on the temporary file
        self.stream.seek(filerec.start + self.startofarcdata)
        tmpfilename = self.__extractsegment(iscompressed=filerec.compressed,
                                            numbytes=filerec.csize)
        if tmpfilename is None:
            raise Error("Error extracting archived file")
        tmpfile = open(tmpfilename, "rb")

        # Compute the CRC32 on the uncompressed file
        streamcrc = _xgutils.streamcrc32(tmpfile)
        if streamcrc != filerec.crc:
            raise Error("File CRC check failed - file corrupt")

        return tmpfile, tmpfilename

    def setblocksize(self, blksize):
        self.__MAXBUFSIZE = blksize


if __name__ == '__main__':
    pass
