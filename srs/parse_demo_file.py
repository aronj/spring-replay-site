#!/usr/bin/env python

# This file is part of the "spring relay site / srs" program. It is published
# under the GPLv3.
#
# Copyright (C) 2012 Daniel Troeder (daniel #at# admin-box #dot# com)
#
#You should have received a copy of the GNU General Public License
#along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re
import sys
from struct import unpack
from time import localtime, strftime
from datetime import timedelta
import pprint
import magic
import gzip
from script import Script, ScriptAI, ScriptAlly, ScriptGamesetup, ScriptMapoptions, ScriptModoptions, ScriptPlayer, ScriptRestrictions, ScriptTeam

class Parse_demo_file():
    def __init__(self, filename):
        self.filename = filename

    def read_blob(self, seek_size, blob_size):
        self.demofile.seek(seek_size)
        return self.demofile.read(blob_size)

    def read_blob_into_int(self, seek_size, blob_size):
        return unpack('i', self.read_blob(seek_size, blob_size))

    def make_numeric(self, val):
        if val.isdigit():
            return int(val)
        else:
            try:
                return float(val)
            except Exception:
                pass
        return val

    def check_magic(self):
        """
        - may raise IOError when opening a file to read
        """
        filemagic = magic.from_file(self.filename, mime=True)
        if filemagic.endswith("gzip"):
            self.demofile = gzip.open(self.filename, 'rb')
        else:
            self.demofile = open(self.filename, "rb")
        self.header = {}
        self.header['magic'] = self.read_blob(0, 16)
        if not self.header['magic'].startswith("spring demofile"):
            raise Exception("Not a spring demofile.")
        self.demofile.close()

    def parse(self):
        """
        reads data from sdf, populates self.header and self.game_setup
        - may raise IOError when opening a file to read or write
        - may raise Exception when file is not a spring demofile
        """
        filemagic = magic.from_file(self.filename, mime=True)
        if filemagic.endswith("gzip"):
            self.demofile = gzip.open(self.filename, 'rb')
        else:
            self.demofile = open(self.filename, "rb")

        #
        # struct DemoFileHeader from rts/System/LoadSave/demofile.h
        #
        self.header = {}
        self.header['magic'] = self.read_blob(0, 16)                             # char magic[16]; ///< DEMOFILE_MAGIC
        if not self.header['magic'].startswith("spring demofile"):
            raise Exception("Not a spring demofile.")
        self.header['version'] = self.read_blob_into_int(16, 4)[0]               # int version; ///< DEMOFILE_VERSION
        self.header['headerSize'] = self.read_blob_into_int(20, 4)[0]            # int headerSize; ///< Size of the DemoFileHeader, minor version number.
        self.header['versionString'] = self.read_blob(24, 256)                   # char versionString[256]; ///< Spring version string, e.g. "0.75b2", "0.75b2+svn4123"
        self.header['gameID'] = self.read_blob(280, 16)                          # boost::uint8_t gameID[16]; ///< Unique game identifier. Identical for each player of the game.
        self.header['unixTime'] = self.read_blob(296, 8)                         # boost::uint64_t unixTime; ///< Unix time when game was started.
        self.header['scriptSize'] = self.read_blob_into_int(304, 4)[0]           # int scriptSize; ///< Size of startscript.
        self.header['demoStreamSize'] = self.read_blob_into_int(308, 4)[0]       # int demoStreamSize; ///< Size of the demo stream.
        self.header['gameTime'] = self.read_blob_into_int(312, 4)[0]             # int gameTime; ///< Total number of seconds game time.
        self.header['wallclockTime'] = self.read_blob_into_int(316, 4)[0]        # int wallclockTime; ///< Total number of seconds wallclock time.
        self.header['numPlayers'] = self.read_blob_into_int(320, 4)[0]           # int numPlayers; ///< Number of players for which stats are saved.
        self.header['playerStatSize'] = self.read_blob_into_int(324, 4)[0]       # int playerStatSize; ///< Size of the entire player statistics chunk.
        self.header['playerStatElemSize'] = self.read_blob_into_int(328, 4)[0]   # int playerStatElemSize; ///< sizeof(CPlayer::Statistics)
        self.header['numTeams'] = self.read_blob_into_int(332, 4)[0]             # int numTeams; ///< Number of teams for which stats are saved.
        self.header['teamStatSize'] = self.read_blob_into_int(336, 4)[0]         # int teamStatSize; ///< Size of the entire team statistics chunk.
        self.header['teamStatElemSize'] = self.read_blob_into_int(340, 4)[0]     # int teamStatElemSize; ///< sizeof(CTeam::Statistics)
        self.header['teamStatPeriod'] = self.read_blob_into_int(344, 4)[0]       # int teamStatPeriod; ///< Interval (in seconds) between team stats.
        self.header['winningAllyTeamsSize'] = self.read_blob_into_int(348, 4)[0] # int winningAllyTeamsSize; ///< The size of the vector of the winning ally teams

#        self.header['void_swab']            = self.read_blob(352, self.header['headerSize']-352)    # lol?

        script = self.read_blob(self.header['headerSize'], self.header['scriptSize'])

        self.winningAllyTeams = []
        winnning_team = 0
        self.demofile.seek(self.header['headerSize']+self.header['scriptSize']+self.header['demoStreamSize'])
        while winnning_team < self.header['winningAllyTeamsSize']:
            team = unpack('B', self.read_blob(self.demofile.tell(), 1))
            self.winningAllyTeams.append(team[0])
            winnning_team += 1


#        demo_stream = self.read_blob(self.demofile.tell(), self.header['demoStreamSize'])
#        i = 0
#        player_stats = []
#        while i < self.header['numPlayers']:
#            player_stats[i] = self.read_blob(self.demofile.tell(), self.header['playerStatElemSize'])
#            i += 1


        self.demofile.close()

        self.header['magic']         = str(self.header['magic']).partition("\x00")[0]
        self.header['versionString'] = str(self.header['versionString']).partition("\x00")[0]
        self.header['gameID']        = "%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x%02x" % unpack("16B", self.header['gameID'])
        self.header['unixTime']      = "%s" % strftime("%Y-%m-%d %H:%M:%S", localtime(unpack("Q", self.header['unixTime'])[0]))
        self.header['gameTime']      = "%s" % str(timedelta(seconds=self.header['gameTime']))
        self.header['wallclockTime'] = "%s" % str(timedelta(seconds=self.header['wallclockTime']))

        self.game_setup = {'ai': {},
                           'allyteam': {},
                           'mapoptions': {},
                           'modoptions': {},
                           'player': {},
                           'restrict': {},
                           'team': {},
                           'host': {}
                           }

        game = re.match('^\[game\]\n\{(?P<data>.*)\}\n', script, re.DOTALL).groupdict()
        game_data = game['data'].replace('\n', '').replace('[options]{}', '')
        section_iter = re.finditer('\[(?P<name>.*?)\]\{(?P<data>.*?)\}', game_data, re.DOTALL)

        self.script = Script()

        while True:
            try:
                section_ = section_iter.next()
            except StopIteration:
                break
            section = section_.groupdict()
            if section and section['data'].strip():
                if section['name'].startswith('player'):
                    player = ScriptPlayer(section['name'], section['data'])
                    if player.spectator:
                        self.script.spectators[player.name] = player.result()
                    else:
                        self.script.players[player.name] = player.result()
                    self.script.players_script.append(player)
                    self.game_setup["player"][player.num] = player.__dict__
                elif section['name'].startswith('ai'):
                    bot = ScriptAI(section['name'], section['data'])
                    self.script.bots[bot.name][section['name']] = bot.__dict__
                    self.game_setup["ai"] = self.script.bots
                elif section['name'].startswith('allyteam'):
                    ally = ScriptAlly(section['name'], section['data'])
                    self.script.allies.append(ally)
                    self.game_setup["allyteam"][ally.num] = ally.__dict__
                elif section['name'].startswith('team'):
                    team = ScriptTeam(section['name'], section['data'])
                    self.script.teams.append(team)
                    self.game_setup["team"][team.num] = team.__dict__
                elif section['name'] == 'restrict':
                    self.script.restrictions = ScriptRestrictions(section['name'], section['data'])
                    self.game_setup["restrict"] = self.script.restrictions
                elif section['name'] == 'mapoptions':
                    self.script.mapoptions = ScriptMapoptions(section['name'], section['data'])
                    self.game_setup["mapoptions"] = self.script.mapoptions.__dict__
                elif section['name'] == 'modoptions':
                    self.script.modoptions = ScriptModoptions(section['name'], section['data'])
                    self.game_setup["modoptions"] = self.script.modoptions.__dict__
        game_txt = game['data'].split("}")[-1:][0].replace('\n','')
        self.game_setup['host'] = ScriptGamesetup("game_setup_host", game_txt).__dict__
        self.script.other['mapname'] = self.game_setup['host']['mapname']
        self.script.other['modname'] = self.game_setup['host']['gametype']

def main(argv=None):
    if argv is None:
        argv = sys.argv
        if len(argv) == 1:
            print "Usage: %s demofile" % (argv[0])
            return 1
        replay = Parse_demo_file(argv[1])
        replay.parse()

        pp = pprint.PrettyPrinter(depth=6)

        print "#################### header ##########################"
        pp.pprint(replay.header)
        print "################## game_setup ########################"
        pp.pprint(replay.game_setup)
        print "############### winningAllyTeams #####################"
        pp.pprint(replay.winningAllyTeams)
        return 0

if __name__ == "__main__":
    sys.exit(main())
