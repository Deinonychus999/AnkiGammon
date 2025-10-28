#
#   xgstruct.py - classes to read XG file structures
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
#   This code is based upon Delphi data structures provided by
#   Xavier Dufaure de Citres <contact@extremegammon.com> for purposes
#   of interacting with the ExtremeGammon XG file formats. Field
#   descriptions derived from xg_format.pas. The file formats are 
#   published at http://www.extremegammon.com/xgformat.aspx
#

from . import xgutils as _xgutils
import struct as _struct
import os as _os
import uuid as _uuid
import binascii as _binascii


class GameDataFormatHdrRecord(dict):
    SIZEOFREC = 8232

    def __init__(self, **kw):
        defaults = {
            'MagicNumber': 0,             # $484D4752, RM_MAGICNUMBER
            'HeaderVersion': 0,           # version
            'HeaderSize': 0,              # size of the header
            'ThumbnailOffset': 0,         # location of the thumbnail (jpg)
            'ThumbnailSize': 0,           # size in bye of the thumbnail
            'GameGUID': None,             # game id (GUID)
            'GameName': None,             # Unicode game name
            'SaveName': None,             # Unicode save name
            'LevelName': None,            # Unicode level name
            'Comments': None              # Unicode comments
            }                              
        super(GameDataFormatHdrRecord, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
        return self[key]

    def fromstream(self, stream):
        try:
            unpacked_data = \
                    _struct.unpack('<4BiiQiLHHBB6s1024H1024H1024H1024H', 
                    stream.read(self.SIZEOFREC))
        except:
            return None

        self.MagicNumber = bytearray(unpacked_data[0:4][::-1]).decode('ascii')
        self.HeaderVersion = unpacked_data[4]
        if self.MagicNumber != 'HMGR' or self.HeaderVersion != 1:
            return None
            
        self.HeaderSize = unpacked_data[5]
        self.ThumbnailOffset = unpacked_data[6]
        self.ThumbnailSize = unpacked_data[7]
    
        # Convert Delphi 4 component GUID to the 6 components 
        # of a Python GUID.
        guidp1, guidp2, guidp3, guidp4, guidp5 = unpacked_data[8:13]
        guidp6 = int(_binascii.b2a_hex(unpacked_data[13]), 16)
        self.GameGUID = str(_uuid.UUID(fields=(guidp1, guidp2, guidp3,
                            guidp4, guidp5, guidp6)))

        self.GameName = _xgutils.utf16intarraytostr(unpacked_data[14:1038])
        self.SaveName = _xgutils.utf16intarraytostr(unpacked_data[1038:2062])
        self.LevelName = _xgutils.utf16intarraytostr(unpacked_data[2062:3086])
        self.Comments = _xgutils.utf16intarraytostr(unpacked_data[3086:4110])
        return self
        

class TimeSettingRecord(dict):

    SIZEOFREC = 32

    def __init__(self, **kw):
        defaults = {
            'ClockType': 0,                 # 0=None,0=Fischer,0=Bronstein
            'PerGame': False,               # time is for session reset after each game
            'Time1': 0,                     # initial time in sec
            'Time2': 0,                     # time added (fisher) or reverved (bronstrein) per move in sec
            'Penalty': 0,                   # point penalty when running our of time (in point)
            'TimeLeft1': 0,                 # current time left
            'TimeLeft2': 0,                 # current time left
            'PenaltyMoney': 0               # point penalty when running our of time (in point)
            }                              
        super(TimeSettingRecord, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
        return self[key]

    def fromstream(self, stream):
        unpacked_data = _struct.unpack(
            '<lBxxxllllll',
            stream.read(self.SIZEOFREC))
        self.ClockType = unpacked_data[0]
        self.PerGame = bool(unpacked_data[1])
        self.Time1 = unpacked_data[2]
        self.Time2 = unpacked_data[3]
        self.Penalty = unpacked_data[4]
        self.TimeLeft1 = unpacked_data[5]
        self.TimeLeft2 = unpacked_data[6]
        self.PenaltyMoney = unpacked_data[7]
        return self


class EvalLevelRecord(dict):

    SIZEOFREC = 4

    def __init__(self, **kw):
        defaults = {
            'Level': 0,                     # Level used see PLAYERLEVEL table
            'isDouble': False               # The analyze assume double for the very next move
            }
        super(EvalLevelRecord, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
       return self[key]

    def fromstream(self, stream):
        unpacked_data = _struct.unpack(
            '<hBb',
            stream.read(self.SIZEOFREC))
        self.Level = unpacked_data[0]
        self.isDouble = bool(unpacked_data[1])

        return self


class EngineStructBestMoveRecord(dict):

    SIZEOFREC = 2184

    def __init__(self, **kw):
        defaults = {
            'Pos': None,                    # Current position
            'Dice': None,                   # Dice
            'Level': 0,                     # analyze level requested
            'Score': None,                  # current score
            'Cube': 0,                      # cube value 1,2,4, etcc.
            'CubePos': 0,                   # 0: Center 1: Player owns cube -1 Opponent owns cube
            'Crawford': 0,                  # 1 = Crawford   0 = No Crawford
            'Jacoby': 0,                    # 1 = Jacoby   0 = No Jacoby
            'NMoves': 0,                    # number of move (max 32)
            'PosPlayed': None,              # position played
            'Moves': None,                  # move list as From1,dice1, from2,dice2 etc.. -1 show termination of list
            'EvalLevel': None,              # evaluation level of each move
            'Eval': None,                   # eval value of each move
            'Unused': 0,                    # if 1 does not count as a decision
            'met': 0,                       # unused
            'Choice0': 0,                   # 1-ply choice (index to PosPlayed)
            'Choice3': 0                    # 3-ply choice (index to PosPlayed)
            }
        super(EngineStructBestMoveRecord, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
        return self[key]

    def fromstream(self, stream):
        unpacked_data = _struct.unpack(
                '<26bxx2ll2llllll',
                stream.read(68))
        self.Pos = unpacked_data[0:26]
        self.Dice = unpacked_data[26:28]
        self.Level = unpacked_data[28]
        self.Score = unpacked_data[29:31]
        self.Cube = unpacked_data[31]
        self.Cubepos = unpacked_data[32]
        self.Crawford = unpacked_data[33]
        self.Jacoby = unpacked_data[34]
        self.NMoves = unpacked_data[35]

        self.PosPlayed = ()
        for row in range(32):
            unpacked_data = _struct.unpack('<26b', stream.read(26))
            self.PosPlayed += (unpacked_data[0:26],)

        self.Moves = ()
        for row in range(32):
            self.Moves += (_struct.unpack('<8b', stream.read(8))[0:8],)

        self.EvalLevel = ()
        for row in range(32):
            self.EvalLevel += (EvalLevelRecord().fromstream(stream),)

        self.Eval = ()
        for row in range(32):
            unpacked_data = _struct.unpack('<7f', stream.read(28))
            self.Eval += (unpacked_data,)

        unpacked_data = _struct.unpack('<bbbb', stream.read(4))
        self.Unused = unpacked_data[0]
        self.met = unpacked_data[1]
        self.Choice0 = unpacked_data[2]
        self.Choice3 = unpacked_data[3]

        return self


class EngineStructDoubleAction(dict):

    SIZEOFREC = 132

    def __init__(self, **kw):
        defaults = {
            'Pos': None,                    # Current position
            'Level': 0,                     # analyze level performed
            'Score': None,                  # current score
            'Cube': 0,                      # cube value 1,2,4, etcc.
            'CubePos': 0,                   # 0: Center 1: Player owns cube -1 Opponent owns cube
            'Jacoby': 0,                    # 1 = Jacoby   0 = No Jacoby
            'Crawford': 0,                  # 1 = Crawford   0 = No Crawford
            'met': 0,                       # unused
            'FlagDouble': 0,                # 0: Dont double 1: Double
            'isBeaver': 0,                  # is it a beaver if doubled
            'Eval': None,                   # eval value for No double
            'equB': 0.0,                    # equity No Double
            'equDouble': 0.0,               # equity Double/take
            'equDrop': 0.0,                 # equity double/drop (-1)
            'LevelRequest': 0,              # analyze level requested
            'DoubleChoice3': 0,             # 3-ply choice as double+take*2
            'EvalDouble': None              # eval value for Double/Take
            }
        super(EngineStructDoubleAction, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
       return self[key]

    def fromstream(self, stream):
        unpacked_data = _struct.unpack(
                '<26bxxl2llllhhhh7ffffhh7f',
                stream.read(132))
        self.Pos = unpacked_data[0:26]
        self.Level = unpacked_data[26]
        self.Score = unpacked_data[27:29]
        self.Cube = unpacked_data[29]
        self.CubePos = unpacked_data[30]
        self.Jacoby = unpacked_data[31]
        self.Crawford = unpacked_data[32]
        self.met = unpacked_data[33]
        self.FlagDouble = unpacked_data[34]
        self.isBeaver = unpacked_data[35]
        self.Eval = unpacked_data[36:43]
        self.equB = unpacked_data[43]
        self.equDouble = unpacked_data[44]
        self.equDrop = unpacked_data[45]
        self.LevelRequest = unpacked_data[46]
        self.DoubleChoice3 = unpacked_data[47]
        self.EvalDouble = unpacked_data[48:55]

        return self

class HeaderMatchEntry(dict):

    SIZEOFREC = 2560

    def __init__(self, version=0, **kw):
        defaults = {
            'Name': 'MatchInfo',
            'EntryType': GameFileRecord.ENTRYTYPE_HEADERMATCH,
            'SPlayer1': None,              # player name in ANSI string for XG1 compatbility see "Player1" and "Player2" below for unicode
            'SPlayer2': None,
            'MatchLength': 0,              # Match length, 99999 for unlimited
            'Variation': 0,                # 0:backgammon, 1: Nack, 2: Hyper, 3: Longgammon
            'Crawford': False,             # Crawford in use
            'Jacoby': False,               # Jacoby in use
            'Beaver': False,               # Beaver in use
            'AutoDouble': False,           # Automatic double in use
            'Elo1': 0.0,                   # player1 elo
            'Elo2': 0.0,                   # player2 experience
            'Exp1': 0,                     # player1 elo
            'Exp2': 0,                     # player2 experience
            'Date': 0,                     # game date
            'SEvent': None,                # event name, in ANSI string for XG1 compatbility see "event" below for unicode
            'GameId': 0,                   # game ID, if player are swap make gameid:=-GameID
            'CompLevel1': -1,              # Player level: see table at the end (PLAYERLEVEL TABLE)
            'CompLevel2': -1,
            'CountForElo': False,          # outcome of the session will affect elo
            'AddtoProfile1': False,        # outcome of the session will affect player 1 profile
            'AddtoProfile2': False,        # outcome of the session will affect player 2 profile
            'SLocation': None,             # location name, in ANSI string for XG1 compatbility see "location" below for unicode
            'GameMode': 0,                 # game mode : see table at the end (GAMEMODE TABLE)
            'Imported': False,             # game was imported from an site (MAT, CBG etc..)
            'SRound': None,                # round name, in ANSI string for XG1 compatbility see "round" below for unicode
            'Invert': 0,                   # If the board is swap then invert=-invert and MatchID=-MatchID
            'Version': version,            # file version, currently SaveFileVersion
            'Magic': 0x494C4D44,           # must be MagicNumber = $494C4D44;
            'MoneyInitG': 0,               # initial game played from the profile against that opp in money
            'MoneyInitScore': [0, 0],      # initial score from the profile against that opp in money
            'Entered': False,              # entered in profile
            'Counted': False,              # already accounted in the profile elo
            'UnratedImp': False,           # game was unrated on the site it was imported from
            'CommentHeaderMatch': -1,      # index of the match comment header in temp.xgc
            'CommentFooterMatch': -1,      # index of the match comment footer in temp.xgc
            'isMoneyMatch': False,         # was player for real money
            'WinMoney': 0.0,               # amount of money for the winner
            'LoseMoney': 0.0,              # amount of money for the looser
            'Currency': 0,                 # currency code from Currency.ini
            'FeeMoney': 0.0,               # amount of rake
            'TableStake': 0,               # max amount that can be lost -- NOT IMPLEMENTED
            'SiteId': -1,                  # site id from siteinfo.ini
            'CubeLimit': 0,                # v8: maximum cube value
            'AutoDoubleMax': 0,            # v8: maximum c# of time the autodouble can be used
            'Transcribed': False,          # v24: game was transcribed
            'Event': None,                 # v24: Event name (unicode)
            'Player1': None,               # v24: Player1 name (unicode)
            'Player2': None,               # v24: Player2 name (unicode)
            'Location': None,              # v24: Location (unicode)
            'Round': None,                 # v24: Round (unicode)
            'TimeSetting': None,           # v25: Time setting for the game
            'TotTimeDelayMove': 0,         # v26: # of checker play marked for delayed RO
            'TotTimeDelayCube': 0,         # v26: # of checker play marked for delayed RO done
            'TotTimeDelayMoveDone': 0,     # v26: # of checker Cube action marked for delayed RO
            'TotTimeDelayCubeDone': 0,     # v26: # of checker Cube action marked for delayed RO Done
            'Transcriber': None            # v30: Name of the Transcriber (unicode)
            }
        super(HeaderMatchEntry, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
       return self[key]

    def fromstream(self, stream):

        unpacked_data = _struct.unpack(
            '<9x41B41BxllBBBBddlld129BxxxlllBBB129BlB129BxxllLl2lBBB'
            'xllBxxxfflfll', stream.read(612))
        self.SPlayer1 = _xgutils.delphishortstrtostr(unpacked_data[0:41])
        self.SPlayer2 = _xgutils.delphishortstrtostr(unpacked_data[41:82])
        self.MatchLength = unpacked_data[82]
        self.Variation = unpacked_data[83]
        self.Crawford = bool(unpacked_data[84])
        self.Jacoby = bool(unpacked_data[85])
        self.Beaver = bool(unpacked_data[86])
        self.AutoDouble = bool(unpacked_data[87])
        self.Elo1 = unpacked_data[88]
        self.Elo2 = unpacked_data[89]
        self.Exp1 = unpacked_data[90]
        self.Exp2 = unpacked_data[91]
        self.Date = str(_xgutils.delphidatetimeconv(unpacked_data[92]))
        self.SEvent = _xgutils.delphishortstrtostr(unpacked_data[93:222])
        self.GameId = unpacked_data[222]
        self.CompLevel1 = unpacked_data[223]
        self.CompLevel2 = unpacked_data[224]
        self.CountForElo = bool(unpacked_data[225])
        self.AddtoProfile1 = bool(unpacked_data[226])
        self.AddtoProfile2 = bool(unpacked_data[227])
        self.SLocation = _xgutils.delphishortstrtostr(unpacked_data[228:357])
        self.GameMode = unpacked_data[357]
        self.Imported = bool(unpacked_data[358])
        self.SRound = _xgutils.delphishortstrtostr(unpacked_data[359:487])
        self.Invert = unpacked_data[488]
        self.Version = unpacked_data[489]
        self.Magic = unpacked_data[490]
        self.MoneyInitG = unpacked_data[491]
        self.MoneyInitScore = unpacked_data[492:494]
        self.Entered = bool(unpacked_data[494])
        self.Counted = bool(unpacked_data[495])
        self.UnratedImp = bool(unpacked_data[496])
        self.CommentHeaderMatch = unpacked_data[497]
        self.CommentFooterMatch = unpacked_data[498]
        self.isMoneyMatch = bool(unpacked_data[499])
        self.WinMoney = unpacked_data[500]
        self.LoseMoney = unpacked_data[501]
        self.Currency = unpacked_data[502]
        self.FeeMoney = unpacked_data[503]
        self.TableStake = unpacked_data[504]
        self.SiteId = unpacked_data[505]
        if self.Version >= 8:
            unpacked_data = _struct.unpack('<ll', stream.read(8))
            self.CubeLimit = unpacked_data[0]
            self.AutoDoubleMax = unpacked_data[1]
        if self.Version >= 24:
            unpacked_data = _struct.unpack('<Bx129H129H129H129H129H',
                                           stream.read(1292))
            self.Transcribed = bool(unpacked_data[0])
            self.Event = _xgutils.utf16intarraytostr(unpacked_data[1:130])
            self.Player1 = _xgutils.utf16intarraytostr(unpacked_data[130:259])
            self.Player2 = _xgutils.utf16intarraytostr(unpacked_data[259:388])
            self.Location = _xgutils.utf16intarraytostr(unpacked_data[388:517])
            self.Round = _xgutils.utf16intarraytostr(unpacked_data[517:646])
        if self.Version >= 25:
            self.TimeSetting = TimeSettingRecord().fromstream(stream)
        if self.Version >= 26:
            unpacked_data = _struct.unpack('<llll', stream.read(16))
            self.TotTimeDelayMove = unpacked_data[0]
            self.TotTimeDelayCube = unpacked_data[1]
            self.TotTimeDelayMoveDone = unpacked_data[2]
            self.TotTimeDelayCubeDone = unpacked_data[3]
        if self.Version >= 30:
            unpacked_data = _struct.unpack('<129H', stream.read(258))
            self.Transcriber = _xgutils.utf16intarraytostr(
                unpacked_data[0:129])

        return self


class FooterGameEntry(dict):

    SIZEOFREC = 2560

    def __init__(self, **kw):
        defaults = {
            'Name': 'GameFooter',
            'EntryType': GameFileRecord.ENTRYTYPE_FOOTERGAME,
            'Score1g': 0,                   # Final score
            'Score2g': 0,                   # Final score
            'CrawfordApplyg': False,        # will crawford apply next game
            'Winner': 0,                    # who win +1=player1, -1 player 2
            'PointsWon': 0,                 # point scored
            'Termination': 0,               # 0=Drop 1=single 2=gammon 3=Backgamon 
                                            # (0,1,2)+100=Resign  (0,1,2)+1000 settle
            'ErrResign': 0.0,               # error made by resigning (-1000 if not analyze)
            'ErrTakeResign': 0.0,           # error made by accepting the resign (-1000 if not analyze)
            'Eval': None,                   # evaluation of the final position
            'EvalLevel': 0
            }
        super(FooterGameEntry, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
       return self[key]

    def fromstream(self, stream):
        unpacked_data = _struct.unpack('<9xxxxllBxxxlllxxxxdd7dl',
                stream.read(116))
        self.Score1g = unpacked_data[0]
        self.Score2g = unpacked_data[1]
        self.CrawfordApplyg = bool(unpacked_data[2])
        self.Winner = unpacked_data[3]
        self.PointsWon = unpacked_data[4]
        self.Termination = unpacked_data[5]
        self.ErrResign = unpacked_data[6]
        self.ErrTakeResign = unpacked_data[7]
        self.Eval = unpacked_data[8:15]
        self.EvalLevel = unpacked_data[15]
        return self


class MissingEntry(dict):

    SIZEOFREC = 2560

    def __init__(self, **kw):
        defaults = {
            'Name': 'Missing',
            'EntryType': GameFileRecord.ENTRYTYPE_MISSING,
            'MissingErrLuck': 0.0,
            'MissingWinner': 0,
            'MissingPoints': 0
            }
        super(MissingEntry, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
       return self[key]

    def fromstream(self, stream):
        unpacked_data = _struct.unpack('<9xxxxxxxxdll', stream.read(32))
        self.MissingErrLuck = unpacked_data[0]
        self.MissingWinner = unpacked_data[1]
        self.MissingPoints = unpacked_data[2]
        return self


class FooterMatchEntry(dict):

    SIZEOFREC = 2560

    def __init__(self, **kw):
        defaults = {
            'Name': 'MatchFooter',
            'EntryType': GameFileRecord.ENTRYTYPE_FOOTERMATCH,
            'Score1m': 0,                   # Final score of the match
            'Score2m': 0,                   # Final score of the match
            'WinnerM': 0,                   # who win +1=player1, -1 player 2
            'Elo1m': 0.0,                   # resulting elo, player1
            'Elo2m': 0.0,                   # resulting elo, player2
            'Exp1m': 0,                     # resulting exp, player1
            'Exp2m': 0,                     # resulting exp, player2
            'Datem': 0.0                    # Date time of the match end
            }
        super(FooterMatchEntry, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
       return self[key]

    def fromstream(self, stream):
        unpacked_data = _struct.unpack('<9xxxxlllddlld', stream.read(56))
        self.Score1m = unpacked_data[0]
        self.Score2m = unpacked_data[1]
        self.WinnerM = unpacked_data[2]
        self.Elo1m = unpacked_data[3]
        self.Elo2m = unpacked_data[4]
        self.Exp1m = unpacked_data[5]
        self.Exp2m = unpacked_data[6]
        self.Datem = str(_xgutils.delphidatetimeconv(unpacked_data[7]))

        return self


class HeaderGameEntry(dict):

    SIZEOFREC = 2560

    def __init__(self, **kw):
        defaults = {
            'Name': 'GameHeader',
            'EntryType': GameFileRecord.ENTRYTYPE_HEADERGAME,
            'Score1': 0,                    # initial score player1
            'Score2': 0,                    # initial score player1
            'CrawfordApply': False,         # iDoes Crawford apply on that game
            'PosInit': (0,) * 26,           # initial position
            'GameNumber': 0,                # Game number (start at 1)
            'InProgress': False,            # Game is still in progress
            'CommentHeaderGame': -1,        # index of the game comment header in temp.xgc
            'CommentFooterGame': -1,        # index of the game comment footer in temp.xgc
            'NumberOfAutoDoubles': 0        # v26: Number of Autodouble that happen in that game
                                            # note that in the rest of the game the cube still start at 1.
                                            # For display purpose or point calculation add the 2^NumberOfAutoDouble
            }
        super(HeaderGameEntry, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
       return self[key]

    def fromstream(self, stream):
        unpacked_data = _struct.unpack('<9xxxxllB26bxlBxxxlll',
                stream.read(68))
        self.Score1 = unpacked_data[0]
        self.Score2 = unpacked_data[1]
        self.CrawfordApply = bool(unpacked_data[2])
        self.PosInit = unpacked_data[3:29]
        self.GameNumber = unpacked_data[29]
        self.InProgress = bool(unpacked_data[30])
        self.CommentHeaderGame = unpacked_data[31]
        self.CommentFooterGame = unpacked_data[32]
        if self.Version >= 26:
            self.NumberOfAutoDoubles = unpacked_data[33]

        return self


class CubeEntry(dict):

    SIZEOFREC = 2560

    def __init__(self, **kw):
        defaults = {
            'Name': 'Cube',
            'EntryType': GameFileRecord.ENTRYTYPE_CUBE,
            'ActiveP': 0,                   # Active player (1 or 2)
            'Double': 0,                    # player double (0= no, 1=yes)
            'Take': 0,                      # opp take (0= no, 1=yes, 2=beaver )
            'BeaverR': 0,                   # player accept beaver (0= no, 1=yes, 2=raccoon)
            'RaccoonR': 0,                  # player accept raccoon (0= no, 1=yes)
            'CubeB': 0,                     # Cube value 0=center, +1=2 own, +2=4 own ... -1=2 opp, -2=4 opp
            'Position': None,               # initial position
            'Doubled': None,                # Analyze result
            'ErrCube': 0.0,                 # error made on doubling (-1000 if not analyze)
            'DiceRolled': None,             # dice rolled
            'ErrTake': 0.0,                 # error made on taking (-1000 if not analyze)
            'RolloutIndexD': 0,             # index of the Rollout in temp.xgr
            'CompChoiceD': 0,               # 3-ply choice as Double+2*take
            'AnalyzeC': 0,                  # Level of the analyze
            'ErrBeaver': 0.0,               # error made on beavering (-1000 if not analyze)
            'ErrRaccoon': 0.0,              # error made on racconning (-1000 if not analyze)
            'AnalyzeCR': 0,                 # requested Level of the analyze (sometime a XGR+ request will stop at 4-ply when obivous)
            'isValid': 0,                   # invalid decision 0=Ok, 1=error, 2=invalid
            'TutorCube': 0,                 # player initial double in tutor mode (0= no, 1=yes)
            'TutorTake': 0,                 # player initial take in tutor mode (0= no, 1=yes)
            'ErrTutorCube': 0.0,            # error initialy made on doubling (-1000 if not analyze)
            'ErrTutorTake': 0.0,            # error initialy made on taking (-1000 if not analyze)
            'FlaggedDouble': False,         # cube has been flagged
            'CommentCube': -1,              # index of the cube comment in temp.xgc
            'EditedCube': False,            # v24: Position was edited at this point
            'TimeDelayCube': False,         # v26: position is marked for later RO
            'TimeDelayCubeDone': False,     # v26: position later RO has been done
            'NumberOfAutoDoubleCube': 0,    # v27: Number of Autodouble that happen in that game
            'TimeBot': 0,                   # v28: time left for both players
            'TimeTop': 0
            }
        super(CubeEntry, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
       return self[key]

    def fromstream(self, stream):
        unpacked_data = _struct.unpack('<9xxxxllllll26bxx',
                                       stream.read(64))
        self.ActiveP = unpacked_data[0]
        self.Double = unpacked_data[1]
        self.Take = unpacked_data[2]
        self.BeaverR = unpacked_data[3]
        self.RaccoonR = unpacked_data[4]
        self.CubeB = unpacked_data[5]
        self.Position = unpacked_data[6:32]
        self.Doubled = EngineStructDoubleAction().fromstream(stream)
        unpacked_data = _struct.unpack('<xxxxd3Bxxxxxdlllxxxx' \
                                       'ddllbbxxxxxxddBxxxlBBBxlll',
                                       stream.read(116))
        self.ErrCube = unpacked_data[0]
        self.DiceRolled = _xgutils.delphishortstrtostr(unpacked_data[1:4])
        self.ErrTake = unpacked_data[4]
        self.RolloutIndexD = unpacked_data[5]
        self.CompChoiceD = unpacked_data[6]
        self.AnalyzeC = unpacked_data[7]
        self.ErrBeaver = unpacked_data[8]
        self.ErrRaccoon = unpacked_data[9]
        self.AnalyzeCR = unpacked_data[10]
        self.isValid = unpacked_data[11]
        self.TutorCube = unpacked_data[12]
        self.TutorTake = unpacked_data[13]
        self.ErrTutorCube = unpacked_data[14]
        self.ErrTutorTake = unpacked_data[15]
        self.FlaggedDouble = bool(unpacked_data[16])
        self.CommentCube = unpacked_data[17]
        if self.Version >= 24:
            self.EditedCube = bool(unpacked_data[18])
        if self.Version >= 26:
            self.TimeDelayCube = bool(unpacked_data[19])
            self.TimeDelayCubeDone = bool(unpacked_data[20])
        if self.Version >= 27:
            self.NumberOfAutoDoubleCube = unpacked_data[21]
        if self.Version >= 28:
            self.TimeBot = unpacked_data[22]
            self.TimeTop = unpacked_data[23]
        return self


class MoveEntry(dict):

    SIZEOFREC = 2560

    def __init__(self, **kw):
        defaults = {
            'Name:': 'Move',
            'EntryType': GameFileRecord.ENTRYTYPE_MOVE,
            'PositionI': None,              # Initial position
            'PositionEnd': None,            # Final Position
            'ActiveP': 0,                   # active player (1,2)
            'Moves': None,                  # list of move as From1,dice1, from2,dice2 etc.. -1 show termination of list
            'Dice': None,                   # dice rolled
            'CubeA': 0,                     # Cube value 0=center, +1=2 own, +2=4 own ... -1=2 opp, -2=4 opp
            'ErrorM': 0,                    # Not used anymore (not sure)
            'NMoveEval': 0,                 # Number of candidate (max 32)
            'DataMoves': None,              # analyze
            'Played': False,                # move was played
            'ErrMove': 0.0,                 # error made (-1000 if not analyze)
            'ErrLuck': 0.0,                 # luck of the roll
            'CompChoice': 0,                # computer choice (index to DataMoves.moveplayed)
            'InitEq': 0.0,                  # Equity before the roll (for luck purposes)
            'RolloutIndexM': None,          # index of the Rollout in temp.xgr
            'AnalyzeM': 0,                  # level of analyze of the move
            'AnalyzeL': 0,                  # level of analyze for the luck
            'InvalidM': 0,                  # invalid decision 0=Ok, 1=error, 2=invalid
            'PositionTutor': None,          # Position resulting of the initial move
            'Tutor': 0,                     # index of the move played dataMoves.moveplayed
            'ErrTutorMove': 0.0,            # error initialy made (-1000 if not analyze)
            'Flagged': False,               # move has been flagged
            'CommentMove': -1,              # index of the move comment in temp.xgc
            'EditedMove': False,            # v24: Position was edited at this point
            'TimeDelayMove': 0,             # v26: Bit list: position is marked for later RO
            'TimeDelayMoveDone': 0,         # v26: Bit list: position later RO has been done
            'NumberOfAutoDoubleMove': 0     # v27: Number of Autodouble that happen in that game
            }
        super(MoveEntry, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
       return self[key]

    def fromstream(self, stream):
        unpacked_data = _struct.unpack('<9x26b26bxxxl8l2lldl',
                                       stream.read(124))
        self.PositionI = unpacked_data[0:26]
        self.PositionEnd = unpacked_data[26:52]
        self.ActiveP = unpacked_data[52]
        self.Moves = unpacked_data[53:61]
        self.Dice = unpacked_data[61:63]
        self.CubeA = unpacked_data[63]
        self.ErrorM = unpacked_data[64] # Not used
        self.NMoveEval = unpacked_data[65]
        self.DataMoves = EngineStructBestMoveRecord().fromstream(stream)

        unpacked_data = _struct.unpack('<Bxxxddlxxxxd32llll26bbxdBxxxl',
                                       stream.read(220))
        self.Played = bool(unpacked_data[0])
        self.ErrMove = unpacked_data[1]
        self.ErrLuck = unpacked_data[2]
        self.CompChoice = unpacked_data[3]
        self.InitEq = unpacked_data[4]
        self.RolloutIndexM = unpacked_data[5:37]
        self.AnalyzeM = unpacked_data[37]
        self.AnalyzeL = unpacked_data[38]
        self.InvalidM = unpacked_data[39]
        self.PositionTutor = unpacked_data[40:66]
        self.Tutor = unpacked_data[66]
        self.ErrTutorMove = unpacked_data[67]
        self.Flagged = bool(unpacked_data[68])
        self.CommentMove = unpacked_data[69]
        if self.Version >= 24:
            unpacked_data = _struct.unpack('<B', stream.read(1))
            self.EditedMove = bool(unpacked_data[0])
        if self.Version >= 26:
            unpacked_data = _struct.unpack('<xxxLL', stream.read(11))
            self.TimeDelayMove = unpacked_data[0]
            self.TimeDelayMoveDone = unpacked_data[1]
        if self.Version >= 27:
            unpacked_data = _struct.unpack('<l', stream.read(4))
            self.NumberOfAutoDoubleMove = unpacked_data[0]

        return self


class UnimplementedEntry(dict):

    """ Class for record types we have yet to implement
    """

    SIZEOFREC = 2560

    def __init__(self, **kw):
        defaults = {
            'Name': 'Unimplemented'
            }
        super(UnimplementedEntry, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
       return self[key]

    def fromstream(self, stream):
        return self


class GameFileRecord(dict):

    __SIZEOFSRHDR = 9
    __REC_CLASSES = [HeaderMatchEntry, HeaderGameEntry,
                     CubeEntry, MoveEntry,
                     FooterGameEntry, FooterMatchEntry,
                     UnimplementedEntry, MissingEntry]

    ENTRYTYPE_HEADERMATCH, ENTRYTYPE_HEADERGAME, ENTRYTYPE_CUBE, \
            ENTRYTYPE_MOVE, ENTRYTYPE_FOOTERGAME, ENTRYTYPE_FOOTERMATCH, \
            ENTRYTYPE_MISSING, ENTRYTYPE_UNIMPLEMENTED = range(8)

    def __init__(self, version=-1, **kw):
        """ Create a game file record based upon the given file version
        number. The file version is first found in a HeaderMatchEntry
        object. The version needs to be propogated to all other game
        file objects within the same archive.
        """
        defaults = {
            'Name': 'GameFileRecord',
            'EntryType': -1,
            'Record': None,
            'Version': version
            }
        super(GameFileRecord, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
       return self[key]

    def fromstream(self, stream):
        # Read the header. First 8 bytes are unused. 9th byte is record type
        # The record type determines what object to create and load.
        # If we catch a struct.error we have hit the EOF.
        startpos = stream.tell()
        try:
            unpacked_data = _struct.unpack('<8xB',
                                           stream.read(self.__SIZEOFSRHDR))
        except _struct.error:
            return None
        self.EntryType = unpacked_data[0]

        # Back up to the beginning of the record after getting the record
        # type and feed the entire stream back into the corresponding
        # record object.
        stream.seek(-self.__SIZEOFSRHDR, _os.SEEK_CUR)

        # Using the appropriate class, read the data stream
        self.Record = self.__REC_CLASSES[self.EntryType]()
        self.Record.Version = self.Version
        self.Record.fromstream(stream)
        realrecsize = stream.tell() - startpos

        # Each record is actually 2560 bytes long. We need to advance past
        # the unused filler data to be at the start of the next record
        stream.seek(self.Record.SIZEOFREC - realrecsize, _os.SEEK_CUR)

        return self.Record


class RolloutContextEntry(dict):

    SIZEOFREC = 2184

    def __init__(self, **kw):
        defaults = {
            'Name': 'Rollout',
            'EntryType': RolloutFileRecord.ROLLOUTCONTEXT,
            'Truncated': False,             # is truncated
            'ErrorLimited': False,          # stop when CI under "ErrorLimit"
            'Truncate': 0,                  # truncation level
            'MinRoll': 0,                   # minimum games to roll
            'ErrorLimit': 0.0,              # CI to stop the RO
            'MaxRoll': 0,                   # maximum games to roll
            'Level1': 0,                    # checker play Level used before "LevelCut"
            'Level2': 0,                    # checker play Level used on and after "LevelCut"
            'LevelCut': 0,                  # Cutoff for level1 and level2
            'Variance': False,              # use variance reduction
            'Cubeless': False,              # is a cubeless ro
            'Time': False,                  # is time limited
            'Level1C': 0,                   # cube Level used before "LevelCut"
            'Level2C': 0,                   # cube Level used on and after "LevelCut"
            'TimeLimit': 0,                 # limit in time (min)
            'TruncateBO': 0,                # what do do when reaching BO db: 0=nothing; 1=?
            'RandomSeed': 0,                # caculated seed=RandomSeedI+hashpos
            'RandomSeedI': 0,               # used entered seed
            'RollBoth': False,              # roll both line (ND and D/T)
            'SearchInterval': 0.0,          # Search interval used (1=normal, 1.5=large, 2=huge, 4=gigantic)
            'met': 0,                       # unused
            'FirstRoll': False,             # is it a first roll rollout
            'DoDouble': False,              # roll both line (ND and D/T) in multiple rollout
            'Extent': False,                # if the ro is extended
            'Rolled': 0,                    # game rolled
            'DoubleFirst': False,           # a double happens immediatly.
            'Sum1': None,                   # sum of equities for all 36 1st roll
            'SumSquare1': None,             # sum of square equities for all 36 1st roll
            'Sum2': None,                   # D/T sum of equities for all 36 1st roll
            'SumSquare2': None,             # D/T sum of square equities for all 36 1st roll
            'Stdev1': None,                 # Standard deviation for all 36 1st roll
            'Stdev2': None,                 # D/T Stand deviation for all 36 1st roll
            'RolledD': None,                # number of game rolled for all 36 1st roll
            'Error1': 0.0,                  # 95% CI
            'Error2': 0.0,                  # D/T 95% CI
            'Result1': None,                # evaluation of the position
            'Result2': None,                # D/T evaluation of the position
            'Mwc1': 0.0,                    # ND  mwc equivalent of result1[1,6]
            'Mwc2': 0.0,                    # D/T mwc equivalent of result2[1,6]
            'PrevLevel': 0,                 # store the previous analyze level (for deleting RO)
            'PrevEval': None,               # store the previous analyze result (for deleting RO)
            'PrevND': 0,                  # store the previous analyze equities (for deleting RO)
            'PrevD': 0,                   
            'Duration': 0,                # duration in seconds
            'LevelTrunc': 0,                # level used at truncation
            'Rolled2': 0,                   # D/T number of game rolled
            'MultipleMin': 0,               # Multiple RO minimum # of game
            'MultipleStopAll': False,       # Multiple RO stop all if one move reach MultipleStopAllValue
            'MultipleStopOne': False,       # Multiple RO stop one move is reach under MultipleStopOneValue
            'MultipleStopAllValue': 0.0,    # value to stop all RO (for instance 99.9%)
            'MultipleStopOneValue': 0.0,    # value to stop one move(for instance 0.01%)
            'AsTake': False,                # when running ND and D/T if AsTake is true, checker decision are made using the cube position in the D/T line
            'Rotation': 0,                  # 0=36 dice, 1=21 dice (XG1), 2=30 dice (for 1st pos)
            'UserInterrupted': False,       # RO was interrupted by user
            'VerMaj': 0,                    # Major version use for the RO, currently (2.20): 2
            'VerMin': 0                     # Minor version use for the RO, currently (2.10): 10 (no change in RO or engine between 2.10 and 2.20)
            }
        super(RolloutContextEntry, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
       return self[key]

    def fromstream(self, stream):
        unpacked_data = _struct.unpack('<BBxxllxxxxdllllBBBxllLlllBxxx' \
                                       'flBBBxlBxxxxxxx37d37d37d37d37d37d37l' \
                                       'ff7f7fffl7fllllllBBxxffBxxxlBxHH',
                                       stream.read(2174))

        self.Truncated = bool(unpacked_data[0])
        self.ErrorLimited = bool(unpacked_data[1])
        self.Truncate = unpacked_data[2]
        self.MinRoll = unpacked_data[3]
        self.ErrorLimit = unpacked_data[4]
        self.MaxRoll = unpacked_data[5]
        self.Level1 = unpacked_data[6]
        self.Level2 = unpacked_data[7]
        self.LevelCut = unpacked_data[8]
        self.Variance = bool(unpacked_data[9])
        self.Cubeless = bool(unpacked_data[10])
        self.Time = bool(unpacked_data[11])
        self.Level1C = unpacked_data[12]
        self.Level2C = unpacked_data[13]
        self.TimeLimit = unpacked_data[14]
        self.TruncateBO = unpacked_data[15]
        self.RandomSeed = unpacked_data[16]
        self.RandomSeedI = unpacked_data[17]
        self.RollBoth = bool(unpacked_data[18])
        self.SearchInterval = unpacked_data[19]
        self.met = unpacked_data[20]
        self.FirstRoll = bool(unpacked_data[21])
        self.DoDouble = bool(unpacked_data[22])
        self.Extent = bool(unpacked_data[23])
        self.Rolled = unpacked_data[24]
        self.DoubleFirst = bool(unpacked_data[25])
        self.Sum1 = unpacked_data[26:63]
        self.SumSquare1 = unpacked_data[63:100]
        self.Sum2 = unpacked_data[100:137]
        self.SumSquare2 = unpacked_data[137:174]
        self.Stdev1 = unpacked_data[174:211]
        self.Stdev2 = unpacked_data[211:248]
        self.RolledD = unpacked_data[248:285]
        self.Error1 = unpacked_data[285]
        self.Error2 = unpacked_data[286]
        self.Result1 = unpacked_data[287:294]
        self.Result2 = unpacked_data[294:301]
        self.Mwc1 = unpacked_data[301]
        self.Mwc2 = unpacked_data[302]
        self.PrevLevel = unpacked_data[303]
        self.PrevEval = unpacked_data[304:311]
        self.PrevND = unpacked_data[311]
        self.PrevD = unpacked_data[312]
        self.Duration = unpacked_data[313]
        self.LevelTrunc = unpacked_data[314]
        self.Rolled2 = unpacked_data[315]
        self.MultipleMin = unpacked_data[316]
        self.MultipleStopAll = bool(unpacked_data[317])
        self.MultipleStopOne = bool(unpacked_data[318])
        self.MultipleStopAllValue = unpacked_data[319]
        self.MultipleStopOneValue = unpacked_data[320]
        self.AsTake = bool(unpacked_data[321])
        self.Rotation = unpacked_data[322]
        self.UserInterrupted = bool(unpacked_data[323])
        self.VerMaj = unpacked_data[324]
        self.VerMin = unpacked_data[325]

        return self


class RolloutFileRecord(dict):

    ROLLOUTCONTEXT = 0

    def __init__(self, version=-1, **kw):
        """ Create a game file record based upon the given file version
        number. The file version is first found in a HeaderMatchEntry
        object. The version needs to be propogated to all other game
        file objects within the same archive.
        """
        defaults = {
            'Name': 'RolloutFileRecord',
            'EntryType': 0,
            'Record': None,
            'Version': version
            }
        super(RolloutFileRecord, self).__init__(defaults, **kw)

    def __setattr__(self, key, value):
        self[key] = value

    def __getattr__(self, key):
       return self[key]

    def fromstream(self, stream):
        # If we are at EOF then return
        if len(stream.read(1)) <= 0:
            return None

        stream.seek(-1, _os.SEEK_CUR)
        startpos = stream.tell()

        # Using the appropriate class, read the data stream
        self.Record = RolloutContextEntry()
        self.Record.Version = self.Version
        self.Record.fromstream(stream)
        realrecsize = stream.tell() - startpos
        # Each record is actually 2184 bytes long. We need to advance past
        # the unused filler data to be at the start of the next record
        stream.seek(self.Record.SIZEOFREC - realrecsize, _os.SEEK_CUR)

        return self.Record


if __name__ == '__main__':
    pass
