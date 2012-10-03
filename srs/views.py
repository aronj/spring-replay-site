# This file is part of the "spring relay site / srs" program. It is published
# under the GPLv3.
#
# Copyright (C) 2012 Daniel Troeder (daniel #at# admin-box #dot# com)
#
#You should have received a copy of the GNU General Public License
#along with this program.  If not, see <http://www.gnu.org/licenses/>.

from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.http import Http404
from django.contrib.comments import Comment
from django.views.decorators.cache import cache_control

import logging
from types import StringTypes
import datetime

from models import *
from common import all_page_infos
from tables import *
from upload import save_tags, set_autotag, save_desc

logger = logging.getLogger(__package__)

@cache_control(must_revalidate=True, max_age=60)
def index(request):
    c = all_page_infos(request)
    c["newest_replays"] = Replay.objects.all().order_by("-pk")[:10]
    c["news"] = NewsItem.objects.all().order_by('-pk')[:10]
    c["replay_details"] = False
    c["pageunique"] = reduce(lambda x, y: x+y, [str(r.pk) for r in c["newest_replays"]])
    return render_to_response('index.html', c, context_instance=RequestContext(request))

def replays(request):
    replays = Replay.objects.all()
    return replay_table(request, replays, "all %d replays"%replays.count())

def replay_table(request, replays, title, template="lists.html", form=None, ext=None):
    from django_tables2 import RequestConfig

    c = all_page_infos(request)
    if ext:
        for k,v in ext.items():
            c[k] = v
    table = ReplayTable(replays)
    RequestConfig(request, paginate={"per_page": 50}).configure(table)
    c['table'] = table
    c['pagetitle'] = title
    if form: c['form'] = form
    return render_to_response(template, c, context_instance=RequestContext(request))

def all_of_a_kind_table(request, table, title, template="lists.html", intro_text=None):
    from django_tables2 import RequestConfig

    c = all_page_infos(request)
    RequestConfig(request, paginate={"per_page": 50}).configure(table)
    c['table'] = table
    c['pagetitle'] = title
    c['intro_text'] = intro_text
    return render_to_response(template, c, context_instance=RequestContext(request))

#@cache_page(3600 * 24)
def replay(request, gameID):
    c = all_page_infos(request)
    try:
        c["replay"] = Replay.objects.prefetch_related().get(gameID=gameID)
    except:
        raise Http404

    c["allyteams"] = []
    for at in Allyteam.objects.filter(replay=c["replay"]):
        teams = Team.objects.filter(allyteam=at, replay=c["replay"])
        players = Player.objects.filter(team__in=teams).order_by("name")
        if teams:
            c["allyteams"].append((at, players))
    c["specs"] = Player.objects.filter(replay=c["replay"], spectator=True).order_by("name")
    c["upload_broken"] = UploadTmp.objects.filter(replay=c["replay"]).exists()
    c["mapoptions"] = MapOption.objects.filter(replay=c["replay"]).order_by("name")
    c["modoptions"] = ModOption.objects.filter(replay=c["replay"]).order_by("name")
    c["replay_details"] = True

    return render_to_response('replay.html', c, context_instance=RequestContext(request))

def mapmodlinks(request, gameID):
    c = all_page_infos(request)
    try:
        replay = Replay.objects.get(gameID=gameID)
    except:
        raise Http404

    gamename = replay.gametype
    mapname  = replay.map_info.name

    from xmlrpclib import ServerProxy
    try:
        proxy = ServerProxy('http://api.springfiles.com/xmlrpc.php', verbose=False)

        searchstring = {"springname" : gamename.replace(" ", "*"), "category" : "game",
                        "torrent" : False, "metadata" : False, "nosensitive" : True, "images" : False}
        c['game_info'] = proxy.springfiles.search(searchstring)

        searchstring = {"springname" : mapname.replace(" ", "*"), "category" : "map",
                        "torrent" : False, "metadata" : False, "nosensitive" : True, "images" : False}
        c['map_info'] = proxy.springfiles.search(searchstring)
    except:
        c['con_error'] = "Error connecting to springfiles.com. Please retry later, or try searching yourself: <a href=\"http://springfiles.com/finder/1/%s\">game</a>  <a href=\"http://springfiles.com/finder/1/%s\">map</a>."%(gamename, mapname)

    return render_to_response('mapmodlinks.html', c, context_instance=RequestContext(request))

@login_required
@never_cache
def edit_replay(request, gameID):
    from forms import EditReplayForm

    c = all_page_infos(request)
    try:
        replay = Replay.objects.prefetch_related().get(gameID=gameID)
        c["replay"] = replay
    except:
        raise Http404

    if request.user != replay.uploader:
        return render_to_response('edit_replay_wrong_user.html', c, context_instance=RequestContext(request))

    if request.method == 'POST':
        form = EditReplayForm(request.POST)
        if form.is_valid():
            short = request.POST['short']
            long_text = request.POST['long_text']
            tags = request.POST['tags']

            for tag in replay.tags.all():
                if tag.replays() == 1 and tag.pk > 10:
                    # this tag was used only by this replay and is not one of the default ones (see srs/sql/tag.sql)
                    tag.delete()
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
    c["replay_details"] = True

    return render_to_response('edit_replay.html', c, context_instance=RequestContext(request))

def download(request, gameID):
    try:
        rf = Replay.objects.get(gameID=gameID).replayfile
    except:
        raise Http404

    rf.download_count += 1
    rf.save()
    return HttpResponseRedirect(settings.STATIC_URL+"replays/"+rf.filename)

def tags(request):
    table = TagTable(Tag.objects.all())
    return all_of_a_kind_table(request, table, "List of all %d tags"%Tag.objects.count())

def tag(request, reqtag):
    replays = Replay.objects.filter(tags__name=reqtag)
    return replay_table(request, replays, "%d replays with tag '%s'"%(replays.count(), reqtag))

def maps(request):
    table = MapTable(Map.objects.all())
    return all_of_a_kind_table(request, table, "List of all %d maps"%Map.objects.count())

def rmap(request, mapname):
    replays = Replay.objects.filter(map_info__name=mapname)
    return replay_table(request, replays, "%d replays on map '%s'"%(replays.count(), mapname))

def players(request):
    players = []
    for pa in PlayerAccount.objects.all():
        for name in pa.names.split(";"):
            players.append({'name': name,
                            'replay_count': pa.replay_count(),
                            'spectator_count': pa.spectator_count(),
                            'accid': pa.accountid})
    table = PlayerTable(players)
    return all_of_a_kind_table(request, table, "List of all %d players"%len(players))

def player(request, accountid):
    rep = ""
    accounts = []

    try:
        accounts.append(PlayerAccount.objects.get(accountid=accountid))
    except:
        raise Http404
    accounts.extend(PlayerAccount.objects.filter(aka=accounts[0]))

    for account in accounts:
        for a in account.names.split(";"):
            rep += '%s '%a

    players = Player.objects.select_related("replay").filter(account__in=accounts, spectator=False)
    replays = [player.replay for player in players]
    return replay_table(request, replays, "%d replays with player %s"%(len(replays), rep))

def game(request, name):
    game = get_object_or_404(Game, name=name)
    gr_list = [{'name': gr.name, 'replays': Replay.objects.filter(gametype=gr.name).count()} for gr in GameRelease.objects.filter(game=game)]
    table = GameTable(gr_list)
    return all_of_a_kind_table(request, table, "List of all %d versions of game %s"%(len(gr_list), game.name))

def games(request):
    games = []
    for gt in list(set(Replay.objects.values_list('gametype', flat=True))):
        games.append({'name': gt,
                      'replays': Replay.objects.filter(gametype=gt).count()})
    table = GameTable(games)
    return all_of_a_kind_table(request, table, "List of all %d games"%len(games))

def gamerelease(request, gametype):
    replays = Replay.objects.filter(gametype=gametype)
    return replay_table(request, replays, "%d replays of game '%s'"%(replays.count(), gametype))

@never_cache
def search(request):
    from forms import AdvSearchForm

    form_fields = ['text', 'comment', 'tag', 'player', 'spectator', 'maps', 'game', 'matchdate', 'uploaddate', 'uploader']
    query = {}
    ext = {}

    if request.method == 'POST':
        # did we come from the adv search page, or from a search in the top menu?
        if request.POST.has_key("search"):
            # top menu -> search everywhere
            ext["showadvsearch"] = False

            st = request.POST["search"].strip()
            if st:
                for f in form_fields:
                    if f not in ['spectator','matchdate', 'uploaddate']:
                        query[f] = st
                form = AdvSearchForm(query)
            else:
                # empty search field in top menu
                ext["showadvsearch"] = True

                query = None
                form = AdvSearchForm()
        else:
            # advSearch was used
            ext["showadvsearch"] = True

            form = AdvSearchForm(request.POST)
            if form.is_valid():
                for f in form_fields:
                    if isinstance(form.cleaned_data[f], StringTypes):
                        # strip() strings, use only non-empty ones
                        if form.cleaned_data[f].strip():
                            query[f] = form.cleaned_data[f].strip()
                    elif form.cleaned_data[f]:
                        query[f] = form.cleaned_data[f]
            else:
                query = None
    else:
        # request.method == GET (display advSearch)
        ext["showadvsearch"] = True

        query = None
        form = AdvSearchForm()

    replays = search_replays(query)

    return replay_table(request, replays, "%d replays matching your search"%replays.count(), "search.html", form, ext)

def search_replays(query):
    """
    I love django Q!!!
    """
    from django.db.models import Q

    if query:
        q = Q()

        for key in query.keys():
            if   key == 'text': q |= Q(title__icontains=query['text']) | Q(long_text__icontains=query['text'])
            elif key == 'comment':
                ct = ContentType.objects.get_for_model(Replay)
                comments = Comment.objects.filter(content_type=ct, comment__icontains=query['comment'])
                c_pks = [c.object_pk for c in comments]
                q |= Q(pk__in=c_pks)
            elif key == 'tag': q |= Q(tags__name__icontains=query['tag'])
            elif key == 'player':
                if query.has_key('spectator'):
                    q |= Q(player__account__names__icontains=query['player'])
                else:
                    q |= Q(player__account__names__icontains=query['player'], player__spectator=False)
            elif key == 'spectator': pass # used in key == 'player'
            elif key == 'maps': q |= Q(map_info__name__icontains=query['maps'])
            elif key == 'game': q |= Q(gametype__icontains=query['game'])
            elif key == 'matchdate':
                start_date = query['matchdate']-datetime.timedelta(1)
                end_date   = query['matchdate']+datetime.timedelta(1)
                q |= Q(unixTime__range=(start_date, end_date))
            elif key == 'uploaddate':
                start_date = query['uploaddate']-datetime.timedelta(1)
                end_date   = query['uploaddate']+datetime.timedelta(1)
                q |= Q(upload_date__range=(start_date, end_date))
            elif key == 'uploader':
                users = User.objects.filter(username__icontains=query['uploader'])
                q |= Q(uploader__in=users)
            else:
                logger.error("Unknown query key: query[%s]=%s",key, query[key])
                raise Exception("Unknown query key: query[%s]=%s"%(key, query[key]))

        if len(q.children):
            replays = Replay.objects.filter(q).distinct()
        else:
            replays = Replay.objects.none()
    else:
        # GET or empty/bad search query
        replays = Replay.objects.none()

    return replays

def win_loss_overview(request):
    c = all_page_infos(request)

    playerlist = list()
    for pa in PlayerAccount.objects.all():
        try:
            name = Player.objects.filter(account=pa).values_list("name")[0][0]
            playerlist.append((pa.accountid, name))
        except:
            pass
    playerlist.sort(key=operator.itemgetter(1))
    c["playerlist"] = playerlist
    return render_to_response('win_loss_overview.html', c, context_instance=RequestContext(request))

@never_cache
def win_loss(request, accountid):
    c = all_page_infos(request)

    pa = get_object_or_404(PlayerAccount, accountid=accountid)
    players = Player.objects.filter(account=pa, spectator=False)
    ats = Allyteam.objects.filter(team__player__in=players)
    at_1v1 = ats.filter(replay__tags__name="1v1")
    at_team = ats.filter(replay__tags__name="Team")
    at_ffa = ats.filter(replay__tags__name="FFA")

    c["at_1v1"] = {"all": at_1v1.count(), "win": at_1v1.filter(winner=True).count(), "loss": at_1v1.filter(winner=False).count()}
    try:
        c["at_1v1"]["ratio"] = "%.02f"%(float(at_1v1.filter(winner=True).count())/at_1v1.filter(winner=False).count())
    except ZeroDivisionError:
        if at_1v1.count() == 0: c["at_1v1"]["ratio"] = "0.00"
        else: c["at_1v1"]["ratio"] = "1.00"

    c["at_team"] = {"all": at_team.count(), "win": at_team.filter(winner=True).count(), "loss": at_team.filter(winner=False).count()}
    try:
        c["at_team"]["ratio"] = "%.02f"%(float(at_team.filter(winner=True).count())/at_team.filter(winner=False).count())
    except ZeroDivisionError:
        if at_team.count() == 0: c["at_team"]["ratio"] = "0.00"
        else: c["at_team"]["ratio"] = "1.00"

    c["at_ffa"] = {"all": at_ffa.count(), "win": at_ffa.filter(winner=True).count(), "loss": at_ffa.filter(winner=False).count()}
    try:
        c["at_ffa"]["ratio"] = "%.02f"%(float(at_ffa.filter(winner=True).count())/at_ffa.filter(winner=False).count())
    except ZeroDivisionError:
        if at_ffa.count() == 0: c["at_ffa"]["ratio"] = "0.00"
        else: c["at_ffa"]["ratio"] = "1.00"

    c["at_all"] = {"all": ats.count(), "win": ats.filter(winner=True).count(), "loss": ats.filter(winner=False).count()}
    try:
        c["at_all"]["ratio"] = "%.02f"%(float(ats.filter(winner=True).count())/ats.filter(winner=False).count())
    except ZeroDivisionError:
        if ats.count() == 0: c["at_all"]["ratio"] = "0.00"
        else: c["at_all"]["ratio"] = "1.00"

    c["playeraccount"] = pa
    return render_to_response('win_loss.html', c, context_instance=RequestContext(request))

@never_cache
def hall_of_fame(request):
    from django_tables2 import RequestConfig

    c = all_page_infos(request)

    c["table_1v1"]     = RatingTable(Rating.objects.filter(match_type="1"), prefix="1-")
    c["table_team"]    = TSRatingTable(Rating.objects.filter(match_type="T"), prefix="t-")
    c["table_ffa"]     = TSRatingTable(Rating.objects.filter(match_type="F"), prefix="f-")
    c["table_teamffa"] = TSRatingTable(Rating.objects.filter(match_type="G"), prefix="g-")
    c["intro_text"]    = ["Ratings are calculated separately for 1v1, Team, FFA and TeamFFA.", "Everyone starts with Elo=1500 (k-factor=24), Glicko=1500 (RD=350) and Trueskill(mu)=25 (sigma=25/3).", "Elo and Glicko (v1) are calculated only for 1v1.", "Glickos rating period is not used atm (I know that' a problem)."]
    c['pagetitle'] = "Hall Of Fame"

    rc = RequestConfig(request, paginate={"per_page": 20})
    rc.configure(c["table_1v1"])
    rc.configure(c["table_team"])
    rc.configure(c["table_ffa"])
    rc.configure(c["table_teamffa"])

    return render_to_response("hall_of_fame.html", c, context_instance=RequestContext(request))

@never_cache
def rating_history(request):
    table = RatingHistoryTable(RatingHistory.objects.all())
    intro_text = ["Ratings are calculated separately for 1v1, Team, FFA and TeamFFA.", "Everyone starts with Elo=1500 (k-factor=24), Glicko=1500 (RD=350) and Trueskill(mu)=25 (sigma=25/3).", "Elo and Glicko (v1) are calculated only for 1v1.", "Glickos rating period is not used atm (I know that' a problem)."]
    return all_of_a_kind_table(request, table, "Rating history", template="wide_list.html", intro_text=intro_text)

@login_required
@never_cache
def user_settings(request):
    # TODO:
    c = all_page_infos(request)
    return render_to_response('settings.html', c, context_instance=RequestContext(request))

def users(request):
    table = UserTable(User.objects.all())
    return all_of_a_kind_table(request, table, "List of all %d uploaders"%User.objects.count())

def see_user(request, username):
    try:
        user = User.objects.get(username=username)
    except:
        raise Http404
    replays = Replay.objects.filter(uploader=user)
    return replay_table(request, replays, "%d replays uploaded by '%s'"%(replays.count(), user))

def match_date(request, shortdate):
    replays = Replay.objects.filter(unixTime__startswith=shortdate)
    return replay_table(request, replays, "%d replays played on '%s'"%(replays.count(), shortdate))

def upload_date(request, shortdate):
    replays = Replay.objects.filter(upload_date__startswith=shortdate)
    return replay_table(request, replays, "%d replays uploaded on '%s'"%(replays.count(), shortdate))

def all_comments(request):
    table = CommentTable(Comment.objects.all())
    return all_of_a_kind_table(request, table, "List of all %d comments"%Comment.objects.count())

@never_cache
def login(request):
    import django.contrib.auth
    from django.contrib.auth.forms import AuthenticationForm

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

@never_cache
def logout(request):
    import django.contrib.auth

    username = str(request.user)
    django.contrib.auth.logout(request)
    logger.info("Logged out user '%s'", username)
    return HttpResponseRedirect("/")
