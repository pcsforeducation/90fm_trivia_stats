# Create your views here.
import logging

import re
from django.http import HttpResponseNotFound, HttpResponseBadRequest
from django.shortcuts import render_to_response
from django.template import RequestContext
from website.models import Score, SMSSubscriberForm, \
    EmailSubscriberForm, SearchForm, get_last_hour, get_last_year, \
    playing_this_year, \
    get_top_ten_teams, TwilioManager, EmailManager
from django.forms.models import model_to_dict

logger = logging.getLogger('logger')


def home(request):
    template_data = {}
    template_data['email_form'] = EmailSubscriberForm()
    template_data['sms_form'] = SMSSubscriberForm()
    template_data['top_teams'] = get_top_ten_teams()
    return render_to_response("homepage.html", template_data,
                              context_instance=RequestContext(request))


# Displays all the information for a team. If year is specified, only for
# that year.
# team_name: str
# team_year: int
def team(request, team_name, team_year=None):
    team_name = team_name.replace('_', ' ')
    template_data = {}
    template_data['team_name'] = team_name.upper()
    template_data['year'] = team_year
    # during = during_trivia()

    # Check to ensure team is playing this year. Otherwise, just show
    # previous years score.
    template_data['playing'] = playing_this_year(team_name)
    template_data['last_hour'] = get_last_hour()
    template_data['last_year'] = get_last_year()

    template_data['scores'] = {}
    scores = Score.objects.filter(team_name=team_name.upper()).order_by(
        '-year')
    if len(scores) == 0:
        return HttpResponseNotFound(
            "Can't find data for team: {0}".format(team_name))
    template_data['scores'] = []
    temp_scores = []
    for year in scores.values_list('year', flat=True).distinct().order_by(
            '-year'):
        temp_scores.append(scores.filter(year=year).order_by('-hour'))
    for year in temp_scores:
        i = 0
        while i + 1 < len(year):
            # print year[i]
            year[i].score_change = year[i].score - year[i + 1].score
            year[i].place_change = year[i + 1].place - year[i].place
            year[i].place_change_abs = abs(year[i].place_change)
            # print "YEAR", year[i].score_change
            i += 1
        template_data['scores'].append(year)
    return render_to_response("team.html", template_data,
                              context_instance=RequestContext(request))


# Displays a list of teams, year combos matching the search.
def search(request):
    template_data = {}
    if request.method == 'POST':
        form = SearchForm(request.POST)
        if form.is_valid():
            search = form.cleaned_data['search']
            t = Score.objects.filter(
                team_name__icontains=search).values_list('team_name',
                                                         'year').distinct(

            ).order_by(
                '-year')
            teams = []
            for team in t:
                url = team[0].replace(' ', '_')
                teams.append(
                    {'team_name': team[0], 'year': team[1], 'url': url})
            template_data['teams'] = teams
        return render_to_response("search_results.html", template_data,
                                  context_instance=RequestContext(request))
    else:
        return HttpResponseBadRequest("Only POSTs allowed.")


# Gives the teams and scores for a certain hour in a year
def year_hour_overview(request, year, hour):
    template_data = {}
    template_data['hour'] = year
    template_data['year'] = hour
    scores = Score.objects.filter(year=year, hour=hour).order_by('-score')
    prev_scores = Score.objects.filter(year=2012).filter(
        hour__lt=hour).values_list('hour', flat=True).distinct().order_by(
        '-hour')
    if len(prev_scores) > 0:
        prev_hour = prev_scores[0]
        prev_hour_scores = Score.objects.filter(year=2012).filter(
            hour=prev_hour)
    else:
        prev_hour = None
    template_data['teams'] = []
    for score in scores:
        team = model_to_dict(score)
        team['url'] = team['team_name'].replace(' ', '_')
        team['score_change'] = 0
        team['place_change'] = 0
        if prev_hour:
            print prev_hour
            prev_team = prev_hour_scores.filter(team_name=team['team_name'])
            if prev_team and len(prev_team) > 0:
                print prev_team[0], prev_team[0].score, team['score'], \
                    prev_team[0].place, team['place']
                team['score_change'] = team['score'] - prev_team[0].score
                team['place_change'] = prev_team[0].place - team['place']
                team['place_change_abs'] = abs(team['place_change'])
        print team
        template_data['teams'].append(team)
    print template_data['teams']
    return render_to_response('hour.html', template_data,
                              context_instance=RequestContext(request))


# List years, and which teams were in first.
def archive(request):
    template_data = {}
    template_data['scores'] = []
    for year in Score.objects.values_list('year',
                                          flat=True).distinct().order_by(
            '-year'):
        template_data['scores'].append(get_top_ten_teams(year, 54))
    return render_to_response("archive.html", template_data,
                              context_instance=RequestContext(request))


# Email/SMS Subscriptions


def email_subscribe(request):
    em = EmailManager()
    return em.email_subscribe(request)


def email_unsubscribe(request):
    pass


def sms_subscribe(request):
    tm = TwilioManager()
    return tm.sms_subscribe(request)


def sms_unsubscribe(request):
    pass


def get_referer_view(request, default=None):
    """
    Return the referer view of the current request
    """
    # if the user typed the url directly in the browser's address bar
    default = '/'
    referer = request.META.get('HTTP_REFERER')
    if not referer:
        return default

    # remove the protocol and split the url at the slashes
    referer = re.sub('^https?:\/\/', '', referer).split('/')
    if referer[0] != request.META.get('SERVER_NAME'):
        return default

    # add the slash at the relative path's view and finished
    referer = u'/' + u'/'.join(referer[1:])
    return referer
