import json
import os
import queue
import threading
from pdb import set_trace
from pprint import pprint

# import DeepDiff as DeepDiff
from threading import Thread

from dateutil import relativedelta
from deepdiff import DeepDiff
import jsonpickle
import sys

import parse_demo_file
import script
from parse_demo_file import Parse_demo_file
from pymongo import MongoClient


class Replay:
    def __init__(self, file_path):
        # sys.stdout.write("\r\b reading replay %s %s\n" % (str(number), game_uuid))
        self.replay_object = Parse_demo_file(file_path)
        self.replay_object.check_magic()
        self.replay_object.parse()

        del self.replay_object.demofile

        self.post_process()

    def get_json_obj(self):
        return json.dumps(self)

    def __str__(self):
        return jsonpickle.encode(self.replay_object, unpicklable=False, keys=False, make_refs=False)

    def get_mongo_object(self):
        mongo = json.loads(jsonpickle.encode(self.replay_object, unpicklable=False, keys=False, make_refs=False))
        return mongo

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
            set_trace()
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

        self.replay_object.unix_time = self.replay_object.header['unixTime']
        del self.replay_object.header['unixTime']

        time_splits = [int(x) for x in self.replay_object.header['gameTime'].split(':')]
        self.replay_object.game_time = time_splits[0]*3600 + time_splits[1]*60 + time_splits[2]
        del self.replay_object.header['gameTime']

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
        # pprint(self.replay_object['game_setup']['team'])
        # set_trace()
        self.replay_object['game_setup']['team'] = [x for x in self.replay_object['game_setup']['team'].values()]


        # bot and win intersect
        if len(set(self.replay_object['winningAllyTeams']) & set(self.replay_object['bots']['teams'])) > 0:
            self.replay_object['bot_won'] = True
        else:
            self.replay_object['bot_won'] = False





        # pprint(self.replay_object, depth=2)
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

        print("Loading replay %s counter %s " % (game_id, counter))
        replay_file_path = os.path.join(replay_folder_path, game_id + '.sdfz')

        replay = Replay(replay_file_path)

        worker_exists = db.replays.find({'gameid': replay_id}, {'_id': 1}).limit(1).count(with_limit_and_skip=True) == 1

        try:
            # result = db.replays.insert_one(replay.get_mongo_object())
            # db.replays.replaceOne({'gameid': game_id}, replay.get_mongo_object())
            # result = db.replays.findOneAndReplace({'gameid': game_id}, replay.get_mongo_object(), {'upsert': True})
            if worker_exists:
                db.replays.update({'gameid': game_id}, replay.get_mongo_object())
            else:
                db.replays.insert(replay.get_mongo_object())
            with counter_lock:
                counter += 1
        except Exception as e:
            # sys.stderr.write(str(replay))
            sys.stdout.write('\n%s\n' % str(e))
            quit()

        replay_queue.task_done()


counter = 0
counter_lock = threading.Lock()

num_worker_threads = 1

replay_queue = queue.Queue()
threads = []
for i in range(num_worker_threads):
    t = threading.Thread(target=replay_worker)
    t.start()
    threads.append(t)


windows_path = 'E:/spring-analysis/replays/'
linux_path = '/mnt/e/spring-analysis/replays/'
replay_folder_path = windows_path if os.name == 'nt' else linux_path
client = MongoClient()
db = client.test

skip_ids = ['ee9145090b95b1dd5f7a3179b8f899']
enabled_ids = ['86532f58ef900f60080edf8f2138a9f3']
full_rerun = True


for number, replay_id in enumerate(os.listdir('%s' % replay_folder_path)):
    replay_id = replay_id.replace('.sdfz', '')

    exists = db.replays.find({'gameid': replay_id}, {'_id': 1}).limit(1).count(with_limit_and_skip=True) == 1

    if full_rerun:
        pass
    elif replay_id not in enabled_ids and (exists or replay_id in skip_ids):
        print('skip or exists %s' % replay_id)
        continue

    replay_queue.put(replay_id)

# block until all tasks are done
replay_queue.join()

# stop workers
for i in range(num_worker_threads):
    replay_queue.put(None)
for t in threads:
    t.join()






    # pprint(db.replays.find({'gameid': game_id}, {'_id': 1}).limit(1).count(with_limit_and_skip=True))

    # replace with new
    # pprint(db.replays.find({'gameid': game_id}, {'_id': 1}).count())

