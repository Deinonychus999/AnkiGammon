#
#   xgimport.py - XG import module
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

from __future__ import with_statement as _with
import tempfile as _tempfile
import shutil as _shutil
import struct as _struct
import os as _os
from . import xgutils as _xgutils
from . import xgzarc as _xgzarc
from . import xgstruct as _xgstruct


class Import(object):

    class Segment(object):
        GDF_HDR, GDF_IMAGE, XG_GAMEHDR, XG_GAMEFILE, XG_ROLLOUTS, XG_COMMENT, \
            ZLIBARC_IDX, XG_UNKNOWN = range(8)
        EXTENSIONS = ['_gdh.bin', '.jpg', '_gamehdr.bin', '_gamefile.bin',
                      '_rollouts.bin', '_comments.bin', '_idx.bin', None]
        GDF_HDR_EXT, GDF_IMAGE_EXT, XG_GAMEHDR_EXT, XG_GAMEFILE_EXT, \
            XG_ROLLOUTS_EXT, XG_COMMENTS_EXT, \
            XG_IDX_EXT, XG_UNKNOWN = EXTENSIONS
        XG_FILEMAP = {'temp.xgi': XG_GAMEHDR, 'temp.xgr': XG_ROLLOUTS,
                      'temp.xgc': XG_COMMENT, 'temp.xg': XG_GAMEFILE}

        XG_GAMEHDR_LEN = 556

        __TMP_PREFIX = 'tmpXGI'

        def __init__(self, type=GDF_HDR, delete=True, prefix=__TMP_PREFIX):
            self.filename = None
            self.fd = None
            self.file = None
            self.type = type
            self.__prefix = prefix
            self.__autodelete = delete
            self.ext = self.EXTENSIONS[type]

        def __enter__(self):
            self.createtempfile()
            return self

        def __exit__(self, type, value, traceback):
            self.closetempfile()

        def closetempfile(self):
            try:
                if self.file is not None:
                    self.file.close()
            finally:
                self.fd = None
                self.file = None
                if self.__autodelete and self.filename is not None and \
                        _os.path.exists(self.filename):
                    try:
                        _os.unlink(self.filename)
                    finally:
                        self.filename = None

        def copyto(self, fileto):
            _shutil.copy(self.filename, fileto)

        def createtempfile(self, mode="w+b"):
            self.fd, self.filename = _tempfile.mkstemp(prefix=self.__prefix)
            self.file = _os.fdopen(self.fd, mode)
            return self

    def __init__(self, filename):
        self.filename = filename

    def getfilesegment(self):
        with open(self.filename, "rb") as xginfile:
            # Extract the uncompressed Game Data Header (GDH)
            # Note: MS Windows Vista feature
            gdfheader = \
                    _xgstruct.GameDataFormatHdrRecord().fromstream(xginfile)
            if gdfheader is None:
                raise Error("Not a game data format file", self.filename)
            
            # Extract the Game Format Header to a temporary file
            with Import.Segment(type=Import.Segment.GDF_HDR) as segment:
                xginfile.seek(0)
                block = xginfile.read(gdfheader.HeaderSize)
                segment.file.write(block)
                segment.file.flush()
                yield segment

            # Extract the uncompressed thumbnail JPEG from the GDF hdr
            if (gdfheader.ThumbnailSize > 0):
                with Import.Segment(type=Import.Segment.GDF_IMAGE) as segment:
                    xginfile.seek(gdfheader.ThumbnailOffset, _os.SEEK_CUR)
                    imgbuf = xginfile.read(gdfheader.ThumbnailSize)
                    segment.file.write(imgbuf)
                    segment.file.flush()
                    yield segment

            # Retrieve an archive object from the stream
            archiveobj = _xgzarc.ZlibArchive(xginfile)

            # Process all the files in the archive
            for filerec in archiveobj.arcregistry:

                # Retrieve the archive file to a temporary file
                segment_file, seg_filename = archiveobj.getarchivefile(filerec)

                # Create a file segment object to passback to the caller
                try:
                    xg_filetype = Import.Segment.XG_FILEMAP[filerec.name]
                except KeyError:
                    # Skip unknown archive files (e.g., temp.xgr2, temp.xgr3, future extensions)
                    # These are typically overflow rollout files or unsupported features
                    segment_file.close()
                    _os.unlink(seg_filename)
                    continue

                xg_filesegment = Import.Segment(type=xg_filetype,
                                                delete=False)
                xg_filesegment.filename = seg_filename
                xg_filesegment.fd = segment_file

                # If we are looking at the game info file then check
                # the magic number to ensure it is valid
                if xg_filetype == Import.Segment.XG_GAMEFILE:
                    segment_file.seek(Import.Segment.XG_GAMEHDR_LEN)
                    magicStr = bytearray(segment_file.read(4)).decode('ascii')
                    if magicStr != 'DMLI':
                        raise Error("Not a valid XG gamefile", self.filename)

                yield xg_filesegment

                segment_file.close()
                _os.unlink(seg_filename)

        return


class Error(Exception):

    def __init__(self, error, filename):
        self.value = "XG Import Error processing '%s': %s" % \
                     (filename, str(error))
        self.error = error
        self.filename = filename

    def __str__(self):
        return repr(self.value)


if __name__ == '__main__':
    pass
