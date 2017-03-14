import os
import re

import time
import sys
import wget
import requests


def dl_replay_href(game_id):
    match = re.search('([\d\w]+)/?$', game_id)
    if match:
        file_name = '/mnt/e/spring-analysis/replays/%s.sdfz' % match.group(1)
        if not os.path.isfile(file_name):
            sys.stdout.write('\n')
            wget.download('http://replays.springrts.com/download/' + game_id, file_name)
            time.sleep(5)

        elif quit_on_hit:
            quit('\nshould now have %s replays' % total_available)
            # if n > 2:
            #     quit()

quit_on_hit = True
offset = 0
page = 1
while True:

    url_recent = 'http://replays.springrts.com/browse_tbl_src?sEcho=3&iColumns=5&sColumns=&iDisplayStart=%s&iDisplayLength=100&mDataProp_0=0&mDataProp_1=function&mDataProp_2=2' \
                  '&mDataProp_3=3' \
                  '&mDataProp_4=4&sSearch=&bRegex=false&sSearch_0=&bRegex_0=false&bSearchable_0=true&sSearch_1=&bRegex_1=false&bSearchable_1=false&sSearch_2=&bRegex_2=false&bSearchable_2=true' \
                  '&sSearch_3=&bRegex_3=false&bSearchable_3=false&sSearch_4=&bRegex_4=false&bSearchable_4=false&iSortCol_0=1&sSortDir_0=desc&iSortingCols=1&bSortable_0=true&bSortable_1=true' \
                  '&bSortable_2=true&bSortable_3=true&bSortable_4=true&btnfilter+game=game+28' % offset
    url_past = 'http://replays.springrts.com/browse_tbl_src?sEcho=3&iColumns=5&sColumns=&iDisplayStart=%s&iDisplayLength=100&mDataProp_0=0&mDataProp_1=function&mDataProp_2=2' \
                  '&mDataProp_3=3&mDataProp_4=4&sSearch=&bRegex=false&sSearch_0=&bRegex_0=false&bSearchable_0=true&sSearch_1=&bRegex_1=false&bSearchable_1=false&sSearch_2=&bRegex_2=false&bSearchable_2=true' \
                  '&sSearch_3=&bRegex_3=false&bSearchable_3=false&sSearch_4=&bRegex_4=false&bSearchable_4=false&iSortCol_0=1&sSortDir_0=asc&iSortingCols=1&bSortable_0=true' \
               '&bSortable_1=true' \
                  '&bSortable_2=true&bSortable_3=true&bSortable_4=true&btnfilter+game=game+28' % offset

    replays_PD_page = requests.get(url_recent)
    # replays_PD_page = requests.get(url_past)

    if replays_PD_page.status_code == 500:
        print('\nprobably reached end')
        break

    # print(replays_PD_page.json())

    replays = replays_PD_page.json()['aaData']

    total_available = replays_PD_page.json()['iTotalRecords']

    if total_available != replays_PD_page.json()['iTotalDisplayRecords']:
        raise Exception

    for n, replay in enumerate(replays):
        sys.stdout.write('\n%s %s/%s %s %s' % (page, n, total_available, replay[1], replay[5]))
        dl_replay_href(replay[5])

    offset += 100
    page += 1
