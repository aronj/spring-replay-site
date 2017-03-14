
import json
import os
import queue
import threading
from pdb import set_trace

import jsonpickle
import sys

import parse_demo_file
import script
from parse_demo_file import Parse_demo_file
from pymongo import MongoClient


class Replay:
    def __init__(self, file_path):
        self.replay_object = Parse_demo_file(file_path)
        self.replay_object.check_magic()
        self.replay_object.parse()
        del self.replay_object.demofile
        self.post_process()

    def get_json_obj(self):
        return json.dumps(self)

    def __str__(self):
        return self.get_replay_jsonpickled()

    def get_mongo_object(self):
        return json.loads(self.get_replay_jsonpickled())

    def get_replay_jsonpickled(self):
        return jsonpickle.encode(self.replay_object, unpicklable=False, keys=False, make_refs=False)

    @staticmethod
    def format_non_nested_builtin(obj):
        if isinstance(obj, (str, int, float)):
            return_obj = obj
        elif isinstance(obj, bytes):
            try:
                return_obj = obj.decode()
            except UnicodeDecodeError as err:
                print('failed byte decoding %s %s' % (obj, err))
                set_trace()
                return_obj = obj
        elif isinstance(obj, type(None)):
            return None
        else:
            raise Exception('unknown type format %s' % obj)
        return return_obj

    def recursive_dict_casting(self, obj):
        if isinstance(obj, dict):
            return {k: self.recursive_dict_casting(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.recursive_dict_casting(elem) for elem in obj]
        elif isinstance(obj, tuple):
            return [self.recursive_dict_casting(elem) for elem in list(obj)]
        elif isinstance(obj, (script.ScriptObject, script.Script, parse_demo_file.Parse_demo_file, script.Result)):
            return {k: self.recursive_dict_casting(v) for k, v in obj.__dict__.items()}
        else:
            return self.format_non_nested_builtin(obj)

    def post_process(self):
        del self.replay_object.additional['chat']
        del self.replay_object.script
        del self.replay_object.game_setup['modoptions']
        del self.replay_object.game_setup['ai']

        '''RENAMES:'''
        # unix_time
        self.replay_object.unix_time = self.replay_object.header['unixTime']
        del self.replay_object.header['unixTime']

        # spring_version
        self.replay_object.spring_version = self.replay_object.header['versionString']
        del self.replay_object.header['versionString']

        try:
            self.replay_object.game_over_frame = int(self.replay_object.game_over)
            del self.replay_object.game_over
        except AttributeError:
            self.replay_object.game_over_frame = None

        self.replay_object.game_id = self.replay_object.gameid
        del self.replay_object.gameid

        # game_time
        time_splits = [int(x) for x in self.replay_object.header['gameTime'].split(':')]
        self.replay_object.game_time = time_splits[0] * 3600 + time_splits[1] * 60 + time_splits[2] + self.replay_object.options['mo_graceperiod']

        self.replay_object = self.recursive_dict_casting(self.replay_object)

        # bots (restructure/flatten)
        bots = self.replay_object['bots']
        del self.replay_object['bots']
        self.replay_object['bots'] = {'teams': [],
                                      'list': []}
        for k, v in bots.items():
            self.replay_object['bots']['list'].append(v)
            self.replay_object['bots']['teams'] = list({v['team']} | set(self.replay_object['bots']['teams']))

        # restructure/mongify key; no "." in key names
        self.replay_object['players'] = [x for x in self.replay_object['players'].values()]
        self.replay_object['spectators'] = [x for x in self.replay_object['spectators'].values()]
        self.replay_object['additional']['faction_change'] = [x for x in self.replay_object['additional']['faction_change'].values()]
        self.replay_object['additional']['kicked'] = [x for x in self.replay_object['additional']['kicked'].values()]
        self.replay_object['additional']['not_connected'] = [x for x in self.replay_object['additional']['not_connected'].values()]
        self.replay_object['additional']['quit'] = [x for x in self.replay_object['additional']['quit'].values()]
        self.replay_object['additional']['timeout'] = [x for x in self.replay_object['additional']['timeout'].values()]
        self.replay_object['game_setup']['allyteam'] = [x for x in self.replay_object['game_setup']['allyteam'].values()]
        self.replay_object['game_setup']['player'] = [x for x in self.replay_object['game_setup']['player'].values()]

        self.replay_object['game_setup']['team'] = [x for x in self.replay_object['game_setup']['team'].values()]

        # bot and win intersect
        if len(set(self.replay_object['winningAllyTeams']) & set(self.replay_object['bots']['teams'])) > 0:
            self.replay_object['bot_won'] = True
        else:
            self.replay_object['bot_won'] = False

        # winning teams contain typical player team value
        if len(self.replay_object['winningAllyTeams']) > 0 and self.replay_object['winningAllyTeams'][0] == 0:
            self.replay_object['players_won'] = True
        else:
            self.replay_object['players_won'] = False

        # something is fishy in here!
        print('bot teams: %s' % self.replay_object['bots']['teams'])
        print('dead teams: %s' % self.replay_object['dead_teams'])
        print('winningAllyTeams: %s' % self.replay_object['winningAllyTeams'])
        # print('numallies, num: %s' % [(vars(x)['numallies'], vars(x)['num']) for x in self.rep_obj['allies']])
        print('bot allyteam? %s' % [x['allyteam'] for x in self.replay_object['game_setup']['team']])


def replay_worker():
    global counter
    while True:
        game_id = replay_queue.get()
        if game_id is None:
            break

        print("Loading replay %s %s/~%s" % (game_id, counter, replay_queue.qsize()))
        replay_file_path = os.path.join(replay_folder_path, game_id + '.sdfz')

        replay = Replay(replay_file_path)

        replay_exists = db.replays.find({'game_id': game_id}, {'_id': 1}).limit(1).count(with_limit_and_skip=True) == 1

        try:
            if replay_exists:
                print('updating %s' % game_id)
                db.replays.update({'game_id': game_id}, replay.get_mongo_object(), True)
            else:
                print('inserting %s' % game_id)
                db.replays.insert(replay.get_mongo_object())
            with counter_lock:
                counter += 1
        except Exception as e:
            # sys.stderr.write(str(replay))
            sys.stdout.write('\n%s\n' % str(e))
            quit()

        replay_queue.task_done()


def set_replays(full_rerun=False, force_ids=None, skip_ids=None, skip_checkpoint_id=None):
    if force_ids is None:
        force_ids = []

    if skip_ids is None:
        skip_ids = []
    skip_ids = set(skip_ids + ['ee9145090b95b1dd5f7a3179b8f899'])

    if skip_checkpoint_id is not None:
        skip_checkpoint_reached = False
    else:
        skip_checkpoint_reached = True

    replay_files = os.listdir('%s' % replay_folder_path)
    for number, replay_id in enumerate(replay_files):
        nat_number = number + 1
        replay_id = replay_id.replace('.sdfz', '')

        if skip_checkpoint_id is not None and replay_id == skip_checkpoint_id:
            skip_checkpoint_reached = True
            # continue

        if not skip_checkpoint_reached:
            continue

        replay_exists = db.replays.find({'game_id': replay_id}, {'_id': 1}).limit(1).count(with_limit_and_skip=True) == 1

        if full_rerun:
            pass
        elif replay_id not in force_ids and (replay_exists or replay_id in skip_ids):
            print('Parse Check DB skip %s %s/%s' % (replay_id, nat_number, len(replay_files)))
            continue
        print('Parse Check DB add  %s %s/%s' % (replay_id, nat_number, len(replay_files)))

        # if replay_queue.qsize() > 9001:
        #     break

        replay_queue.put(replay_id)


def run():
    set_replays(full_rerun=True, skip_checkpoint_id='92b96f581b4aeb6ff0bb650a6801a947')

    num_worker_threads = 1
    threads = []
    for i in range(num_worker_threads):
        t = threading.Thread(target=replay_worker)
        t.start()
        threads.append(t)

    # block until all tasks are done
    replay_queue.join()
    # stop workers
    for i in range(num_worker_threads):
        replay_queue.put(None)
    for t in threads:
        t.join()


windows_path = 'E:/spring-analysis/replays/'
linux_path = '/mnt/e/spring-analysis/replays/'
replay_folder_path = windows_path if os.name == 'nt' else linux_path
client = MongoClient()
db = client.test
replay_queue = queue.Queue()
counter = 0
counter_lock = threading.Lock()

run()
