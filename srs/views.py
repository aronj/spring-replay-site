# This file is part of the "spring relay site / srs" program. It is published
# under the GPLv3.
#
# Copyright (C) 2012 Daniel Troeder (daniel #at# admin-box #dot# com)
#
#You should have received a copy of the GNU General Public License
#along with this program.  If not, see <http://www.gnu.org/licenses/>.

from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.core.context_processors import csrf
from django.template import RequestContext
from django.db.models import Count
from django.contrib.auth.decorators import login_required
import django.contrib.auth
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Q
from django.http import Http404
from django.contrib.comments import Comment
from django_tables2 import RequestConfig

from tempfile import mkstemp
import os
import sets
import shutil
import functools
import locale
import logging
import operator

from models import *
from common import all_page_infos
from forms import EditReplayForm
from tables import *
from upload import save_tags, set_autotag, save_desc

logger = logging.getLogger(__package__)


def index(request):
    c = all_page_infos(request)
    c["newest_replays"] = Replay.objects.all().order_by("-pk")[:10]
    c["news"] = NewsItem.objects.all().order_by('-pk')[:10]
    return render_to_response('index.html', c, context_instance=RequestContext(request))

def replays(request):
    c = all_page_infos(request)
    table = ReplayTable(Replay.objects.all())
    RequestConfig(request, paginate={"per_page": 50}).configure(table)
    c['table'] = table
    c['pagetitle'] = "replays"
    c['long_table'] = True
    return render_to_response('lists.html', c, context_instance=RequestContext(request))

def replay(request, gameID):
    c = all_page_infos(request)
    try:
        c["replay"] = Replay.objects.prefetch_related().get(gameID=gameID)
    except:
        # TODO: nicer error handling
        raise Http404

    c["allyteams"] = []
    for at in Allyteam.objects.filter(replay=c["replay"]):
        teams = Team.objects.prefetch_related("teamleader").filter(allyteam=at, replay=c["replay"])
        if teams:
            c["allyteams"].append((at, teams))
    c["specs"] = Player.objects.filter(replay=c["replay"], spectator=True)

    return render_to_response('replay.html', c, context_instance=RequestContext(request))

@login_required
def edit_replay(request, gameID):
    c = all_page_infos(request)
    try:
        replay = Replay.objects.prefetch_related().get(gameID=gameID)
        c["replay"] = replay
    except:
        # TODO: nicer error handling
        raise Http404

    if request.user != replay.uploader:
        return render_to_response('edit_replay_wrong_user.html', c, context_instance=RequestContext(request))

    if request.method == 'POST':
        form = EditReplayForm(request.POST)
        if form.is_valid():
            short = request.POST['short']
            long_text = request.POST['long_text']
            tags = request.POST['tags']

            replay.tags.clear()
            autotag = set_autotag(replay)
            save_tags(replay, tags)
            save_desc(replay, short, long_text, autotag)
            replay.save()
            logger.info("User '%s' modified replay '%s': short: '%s' title:'%s' long_text:'%s' tags:'%s'",
                        request.user, replay.gameID, replay.short_text, replay.title, replay.long_text, reduce(lambda x,y: x+", "+y, [t.name for t in Tag.objects.filter(replay=replay)]))
            return HttpResponseRedirect(replay.get_absolute_url())
    else:
        form = EditReplayForm({'short': replay.short_text, 'long_text': replay.long_text, 'tags': reduce(lambda x,y: x+", "+y, [t.name for t in Tag.objects.filter(replay=replay)])})
    c['form'] = form

    return render_to_response('edit_replay.html', c, context_instance=RequestContext(request))

def download(request, gameID):
    # TODO
    c = all_page_infos(request)
    try:
        rf = Replay.objects.get(gameID=gameID).replayfile
    except:
        # TODO: nicer error handling
        raise Http404

    rf.download_count += 1
    rf.save()
    return HttpResponseRedirect(settings.STATIC_URL+"replays/"+rf.filename)

def tags(request):
    c = all_page_infos(request)
    table = TagTable(Tag.objects.all())
    RequestConfig(request, paginate={"per_page": 50}).configure(table)
    c['table'] = table
    c['pagetitle'] = "tags"
    return render_to_response('lists.html', c, context_instance=RequestContext(request))

def tag(request, reqtag):
    # TODO
    c = all_page_infos(request)
    rep = "<b>TODO</b><br/><br/>list of games with tag '%s':<br/>"%reqtag
    for replay in Replay.objects.filter(tags__name=reqtag):
        rep += '* <a href="%s">%s</a><br/>'%(replay.get_absolute_url(), replay.__unicode__())
    rep += '<br/><br/><a href="/">Home</a>'
    return HttpResponse(rep)

def maps(request):
    c = all_page_infos(request)
    table = MapTable(Map.objects.all())
    RequestConfig(request, paginate={"per_page": 50}).configure(table)
    c['table'] = table
    c['pagetitle'] = "maps"
    return render_to_response('lists.html', c, context_instance=RequestContext(request))

def rmap(request, mapname):
    # TODO
    c = all_page_infos(request)
    rep = "<b>TODO</b><br/><br/>list of games on map '%s':<br/>"%mapname
    for replay in Replay.objects.filter(map_info__name=mapname):
        rep += '* <a href="%s">%s</a><br/>'%(replay.get_absolute_url(), replay.__unicode__())
    rep += '<br/><br/><a href="/">Home</a>'
    return HttpResponse(rep)

def players(request):
    c = all_page_infos(request)
    players = []
    for pa in PlayerAccount.objects.all():
        for name in pa.names.split(";"):
            players.append({'name': name,
                            'replay_count': pa.replay_count(),
                            'spectator_count': pa.spectator_count(),
                            'accid': pa.accountid})
    table = PlayerTable(players)
    RequestConfig(request, paginate={"per_page": 50}).configure(table)
    c['table'] = table
    c['pagetitle'] = "players"
    return render_to_response('lists.html', c, context_instance=RequestContext(request))

def player(request, accountid):
    # TODO
    c = all_page_infos(request)
    rep = "<b>TODO</b><br/><br/>This player is know as:<br/>"
    accounts = []

    try:
        accounts.append(PlayerAccount.objects.get(accountid=accountid))
    except:
        # TODO: nicer error handling
        raise Http404
    accounts.extend(PlayerAccount.objects.filter(aka=accounts[0]))
    for account in accounts:
        for a in account.names.split(";"):
            rep += '* %s<br/>'%a

    players = Player.objects.select_related("replay").filter(account__in=accounts)
    rep += "<br/><br/>This player (with one of his accounts/aliases) has played in these games:<br/>"
    for player in players:
        rep += '* <a href="%s">%s</a>'%(player.replay.get_absolute_url(), player.replay.__unicode__())
        if player.spectator:
            rep += ' (spec)'
        rep += '<br/>'
    rep += '<br/><br/><a href="/">Home</a>'
    return HttpResponse(rep)

def games(request):
    c = all_page_infos(request)
    games = []
    for gt in list(set(Replay.objects.values_list('gametype', flat=True))):
        games.append({'name': gt,
                      'replays': Replay.objects.filter(gametype=gt).count()})
    table = GameTable(games)
    RequestConfig(request, paginate={"per_page": 50}).configure(table)
    c['table'] = table
    c['pagetitle'] = "games"
    return render_to_response('lists.html', c, context_instance=RequestContext(request))
def game(request, gametype):
    # TODO
    c = all_page_infos(request)
    rep = "<b>TODO</b><br/><br/>list of replays of game %s:<br/>"%gametype
    for replay in Replay.objects.filter(gametype=gametype):
        rep += '* <a href="%s">%s</a><br/>'%(replay.get_absolute_url(), replay.__unicode__())
    rep += '<br/><br/><a href="/">Home</a>'
    return HttpResponse(rep)

def search(request):
    # TODO
    c = all_page_infos(request)
    resp = "<b>TODO</b><br/><br/>"
    if request.method == 'POST':
        st = request.POST["search"].strip()
        if st:
            users = User.objects.filter(username__icontains=st)
            replays = Replay.objects.filter(Q(gametype__icontains=st)|
                                            Q(title__icontains=st)|
                                            Q(short_text__icontains=st)|
                                            Q(long_text__icontains=st)|
                                            Q(map_info__name__icontains=st)|
                                            Q(tags__name__icontains=st)|
                                            Q(uploader__in=users)|
                                            Q(player__account__names__icontains=st)).distinct()

            resp += 'Your search for "%s" yielded %d results:<br/><br/>'%(st, replays.count())
            for replay in replays:
                resp += '* <a href="%s">%s</a><br/>'%(replay.get_absolute_url(), replay.__unicode__())
        else:
            HttpResponseRedirect("/search/")
    return HttpResponse(resp)

@login_required
def user_settings(request):
    # TODO:
    c = all_page_infos(request)
    return render_to_response('settings.html', c, context_instance=RequestContext(request))

def users(request):
    c = all_page_infos(request)
    table = UserTable(User.objects.all())
    RequestConfig(request, paginate={"per_page": 50}).configure(table)
    c['table'] = table
    c['pagetitle'] = "users"
    return render_to_response('lists.html', c, context_instance=RequestContext(request))

def see_user(request, username):
    # TODO:
    rep = "<b>TODO</b><br/><br/>"
    user = User.objects.get(username=username)
    try:
        rep += "list of replays uploaded by %s:<br/>"%username
        for replay in Replay.objects.filter(uploader=user):
            rep += '* <a href="%s">%s</a><br/>'%(replay.get_absolute_url(), replay.__unicode__())
    except:
        rep += "user %s unknown.<br/>"%username
    rep += '<br/><br/><a href="/">Home</a>'
    return HttpResponse(rep)

def match_date(request, shortdate):
    # TODO:
    rep = "<b>TODO</b><br/><br/>"
    rep += "list of replays played on %s:<br/>"%shortdate
    for replay in Replay.objects.filter(unixTime__startswith=shortdate):
        rep += '* <a href="%s">%s</a><br/>'%(replay.get_absolute_url(), replay.__unicode__())
    rep += '<br/><br/><a href="/">Home</a>'
    return HttpResponse(rep)

def upload_date(request, shortdate):
    # TODO:
    rep = "<b>TODO</b><br/><br/>"
    rep += "list of replays uploaded on %s:<br/>"%shortdate
    for replay in Replay.objects.filter(upload_date__startswith=shortdate):
        rep += '* <a href="%s">%s</a><br/>'%(replay.get_absolute_url(), replay.__unicode__())
    rep += '<br/><br/><a href="/">Home</a>'
    return HttpResponse(rep)

def all_comments(request):
    c = all_page_infos(request)
    table = CommentTable(Comment.objects.all())
    RequestConfig(request, paginate={"per_page": 50}).configure(table)
    c['table'] = table
    c['pagetitle'] = "comments"
    c['long_table'] = True
    return render_to_response('lists.html', c, context_instance=RequestContext(request))

def login(request):
    c = all_page_infos(request)
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = django.contrib.auth.authenticate(username=form.cleaned_data["username"], password=form.cleaned_data["password"])
            if user is not None:
                if user.is_active:
                    django.contrib.auth.login(request, user)
                    logger.info("Logged in user '%s'", request.user)
                    nexturl = request.GET.get('next')
                    # TODO: "next" is never passed...
                    if nexturl:
                        dest = nexturl
                    else:
                        dest = "/"
                    return HttpResponseRedirect(dest)
    else:
        form = AuthenticationForm()
    c['form'] = form
    return render_to_response('login.html', c, context_instance=RequestContext(request))

def logout(request):
    username = str(request.user)
    django.contrib.auth.logout(request)
    logger.info("Logged out user '%s'", username)
    return HttpResponseRedirect("/")
