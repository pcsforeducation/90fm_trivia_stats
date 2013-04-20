from django.db import models
from django.contrib.localflavor.us.forms import USPhoneNumberField
from django.forms import ModelForm, Form, CharField, EmailField
from django.conf import settings
from BeautifulSoup import BeautifulStoneSoup, BeautifulSoup
import datetime
from twilio.rest import TwilioRestClient
from twilio import TwilioRestException
import re
import urllib2
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseNotFound, HttpResponseServerError
from django.shortcuts import render_to_response, redirect
from django.template import RequestContext, Context
# from website.models import Score, AvailableHours, Settings,
# SMSSubscriberForm, EmailSubscriberForm, EmailSubscriber, SMSSubscriber,
# SearchForm
from BeautifulSoup import BeautifulStoneSoup, BeautifulSoup
import sys
import os
import time
import datetime
# import settings
from django.core.mail import send_mail
from django.template.loader import get_template

from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from django.template.loader import render_to_string
import smtplib
from django.db import transaction
from pygooglechart import XYLineChart
# import twitter
import boto.ses as ses
ses_conn = ses.connect_to_region('us-east-1')
from django.conf import settings
from django.db import IntegrityError
import logging
logger = logging.getLogger('logger')

class Score(models.Model):
    # This should be team_name for consistency..
    team_name = models.CharField(max_length=255, db_index=True)
    year = models.IntegerField()
    hour = models.IntegerField(db_index=True)
    place = models.IntegerField(db_index=True)
    score = models.IntegerField(db_index=True)
    score_change = 0
    place_change = 0
    place_change_abs = 0

    def url(self):
        return self.team_name.replace(' ', '_')

    def __unicode__(self):
        return 'Team: %s, %d Hour %d' % (self.team_name, self.year, self.hour)

    class Meta:
        unique_together = (("team_name", "hour", "year"))


class TwilioManager(object):
    def get_twilio_account(self):
        return settings.TWILIO_ACCOUNT

    def get_twilio_token(self):
        return settings.TWILIO_AUTH

    def get_twilio_number(self):
        return settings.TWILIO_NUMBER

    def sms_notify(self, hour=None, debug=False):
        account = self.get_twilio_account()
        token = self.get_twilio_token()
        from_number = self.get_twilio_number()

        if account is None or token is None or from_number is None:
            logger.error("Missing token, account, or from_number")
            return

        client = TwilioRestClient(account, token)
        if client is None:
            logger.error("Client failed.")
            return

        # if hour is None:
        hour = get_last_hour()
        for user in SMSSubscriber.objects.all():
            if user.team_name:
                score = Score.objects.filter(hour=hour).filter(team_name=user.team_name)
                if len(score) != 1:
                    logger.warning("Failed sms notify for hour %d for team name %s, %d scores found.." % (int(hour), user.team_name, len(score)))
                    continue
                else:
                    try:
                        score = score[0]
                        # Max length of team name is 36
                        # 88 in characters (including spaces), 2 for hour, 3 for place, 5 for
                        # points = 134 max characters.
                        if not debug:
                            client.sms.messages.create(to=user.phone_number, from_=from_number, body="Trivia Scores for Hour %d. %s in %d place with %d points. Check scores at http://triviastats.com." % (hour, user.team_name, score.place, score.score))
                            logger.info("Sent SMS to: {0}, {1}".format(user.phone_number, user.team_name))
                        else:
                            logger.info("Would have sent SMS to: {0}, {1} for hour {2}".format(user.phone_number, user.team_name, hour))
                        # send_mail('Trivia Scores Updated for Hour %d. %s is in %d place with %d
                        # points.' % (get_current_hour(), score.team_name, score.place,
                        # score.score), 'Trivia scores for Hour %d have been posted. %s is in %d
                        # place with %d points. You can check your current stats at <a
                        # href="http://triviastats.com">TriviaStats.com</a>' %
                        # (get_current_hour(), score.team_name, score.place, score.score),
                        # 'noreply@triviastats.com', user.email, fail_silently=False)
                    except TwilioRestException, e:
                        logger.exception("SMS for user {0} failed.".format(user))
                        return
            else:
                try:
                    # Max length of team name is 36
                    if not debug:
                        client.sms.messages.create(to=user.phone_number, from_=from_number, body="Trivia Scores for Hour %d. Check scores at http://triviastats.com." % (hour, ))
                        logger.info("Sent SMS to: {0}".format(user.phone_number))
                    else:
                        logger.info("Would have sent SMS to: {0} for hour {1}".format(user.phone_number, hour))
                    # send_mail('Trivia Scores Updated for Hour %d' % get_current_hour(),
                    # 'Trivia scores for Hour %d have been posted. You can check your current
                    # stats at <a href="http://triviastats.com">TriviaStats.com</a>' %
                    # get_current_hour(), 'noreply@triviastats.com', user.email,
                    # fail_silently=False)
                except TwilioRestException, e:
                    logger.exception("SMS for user {0} failed.".format(user))
                    return

    def sms_update(self,):
        hour = get_last_hour()
        for sub in SMSSubscriber.objects.all():
            if sub.phone_number == None:
                continue
            score = None
            if sub.team_name:

                try:
                    score = Score.objects.filter(team_name=sub.team_name.upper().get(hour=get_last_hour()))
                except Exception, e:
                    logger.exception("Team name {0} doesn't exist or has too many returned for SMS: {1}".format(sub.team_name, sub.phone_number))
            if score:
                text_content = "%s Score: %d Place: %d. See more at TriviaStats.com/hour/%d" % (
                    sub.team_name, score.score, score.place, hour)
            else:
                text_content = "Trivia Stats: Scores for Hour %d have been updated. See them at TriviaStats.com/hour/%d" % (hour, hour)
            client = TwilioRestClient(settings.TWILIO_ACCOUNT, settings.TWILIO_AUTH)
            message = client.sms.messages.create(to=sub.phone_number, from_=settings.TWILIO_NUMBER, body=text_content)
            logger.info('message sent to user: {0}'.format(sub.phone_number))

    def sms_subscribe(self, request):
        if request.method == 'POST':
            form = SMSSubscriberForm(request.POST)
            if form.is_valid():
                if 'team_name' in form.cleaned_data:
                    team_name = form.cleaned_data['team_name'].upper()
                else:
                    team_name = None
                number = self.clean_number(form.cleaned_data['phone_number'])
                if number == None:
                    logger.warning("Need a phone_number!")
                    return HttpResponseServerError("Invalid phone number")
                sub = SMSSubscriber(team_name=team_name, phone_number=number)
                if len(SMSSubscriber.objects.filter(phone_number=number)) > 0:
                    logger.warning("Duplicate Phone Number: {0}".format(number))
                    messages.error(request, "Cannot register multiple times for phone number: {0}".format(number))
                    return redirect('/')
                try:
                    sub.save()
                except Exception as e:
                    logger.warning("Duplicate Phone Number: {0}".format(number))
                    messages.error(request, "Cannot register multiple times for phone number: {0}".format(number))
                    return redirect('/')

                # Notify of subscription
                c = Context({'number': number, 'team_name': team_name})
                text = get_template('subscribe_sms.txt')
                text_content = text.render(c)
                if len(text_content) > 140:
                    logger.warning("More than one message!! Message: {0}".format(text_content))

                client = TwilioRestClient(self.get_twilio_account(), self.get_twilio_token())
                # print client
                # try:
                message = client.sms.messages.create(to=number, from_=settings.TWILIO_NUMBER, body=text_content)
                # except TwilioRestException, e:
                # pass
                if team_name:
                    messages.success(request, "Phone number %s for team %s successfully added!" % (number, team_name))
                else:
                    messages.success(request, "Phone number %s successfully added!" % (number))
                return redirect('/')
            else:
                messages.error(request, 'Invalid Phone Number or Team Name')
                return redirect('/')
        else:
            return redirect('/')

    def sms_unsubscribe(self, request):
        if request.method == 'POST':
            form = SMSUnsubscribeForm(request.POST)
            if form.is_valid():
                number = self.clean_number(form.cleaned_data['phone_number'])
                subscriber = SMSSubscriber.objects.filter(number=number)
                if len(subscriber) != 1:
                    return HttpResponseServerError("Number not subscribed")
                subscriber.delete()
                return redirect('/')

    def clean_number(self, number):
        return number.replace('(', '').replace(')', '').replace('-', '').replace(' ', '')


class EmailManager(object):
    def email_subscribe(self, request):
        if request.method == 'POST':
            form = EmailSubscriberForm(request.POST)
            if form.is_valid():
                if 'team_name' in form.cleaned_data:
                    team_name = form.cleaned_data['team_name'].upper()
                else:
                    team_name = None
                email = form.cleaned_data['email']
                sub = EmailSubscriber(email=email, team_name=team_name)
                if len(EmailSubscriber.objects.filter(email=email)) > 0:
                    logger.warning("Duplicate Email: {0}".format(email))
                    messages.error(request, "Cannot register multiple times for email: {0}".format(email))
                    return redirect('/')
                try:
                    sub.save()
                except Exception as e:
                    logger.warning("Duplicate Email: {0}".format(email))
                    messages.error(request, "Cannot register multiple times for email: {0}".format(email))
                    return redirect('/')

                # Notify of subscription
                c = Context({'email': email, 'team_name': team_name})
                text = get_template('subscribe_email.txt')
                text_content = text.render(c)
                html = get_template('subscribe_email.html')
                html_content = text.render(c)
                subject = "Thank you for subscribing to Trivia Stats Notification System!"
                # send_mail(subject, text_content, settings.EMAIL_FROM_ADDRESS, [email])
                # try:
                msg = EmailMultiAlternatives(subject, text_content, settings.EMAIL_FROM_ADDRESS, [email])
                msg.attach_alternative(html_content, "text/html")
                msg.send()
                # except Exception as e:
                #     print e
                #     return HttpResponse(e)
                if team_name:
                    messages.success(request, "Email {0} for team {1} successfully added!".format(email, team_name))
                else:
                    messages.success(request, "Email {0} successfully added!".format(email))
            else:
                # TODO add message about why this doesn't work
                logger.warning('Invalid Email or Team Name')
                messages.error(request, 'Invalid Email or Team Name')
            return redirect('/')

    def email_unsubscribe(self, request):
        if request.method == 'POST':
            form = EmailUnsubscribeForm(request.POST)
            if form.is_valid():
                subscriber = EmailSubscriber.objects.filter(email=form.cleaned_data['email'])
                if len(subscriber) == 0:
                    return HttpResponseServerError("Email not subscribed")
                elif len(subscriber) > 1:
                    for sub in subscriber:
                        sub.delete()
                else:
                    subscriber.delete()
                return redirect('/')

    def email_notify(self, hour=None, debug=False):
        year = get_last_year()
        hour = get_last_hour()
        for user in EmailSubscriber.objects.all():
            if user.team_name:
                score = Score.objects.filter(year=year).filter(hour=hour).filter(team_name=user.team_name.strip())
                if len(score) != 1:
                    logger.error("Failed email notify for hour {0} for team name {1}. Found {2} scores.".format(int(hour), user.team_name.strip(), len(score)))
                    continue
                else:
                    score = score[0]
                    try:
                        if not debug:
                            send_mail(subject='Trivia Scores Updated for Hour %d. %s is in %d place with %d points.' % (hour, user.team_name, score.place, score.score), message='Trivia scores for Hour %d have been posted. %s is in %d place with %d points. You can check your current stats at <a href="http://triviastats.com/team/%s">TriviaStats.com</a>' % (hour, user.team_name, score.place, score.score, user.team_name.replace(' ', '_')), from_email='noreply@triviastats.com', recipient_list=[user.email, ], fail_silently=False)
                            logger.info("Sent email to {0}: {1}".format(user.email, user.team_name))
                        else:
                            logger.info("Would have sent email to {0}: {1} for hour {2}".format(user.email, user.team_name, hour))
                    except smtplib.SMTPException, e:
                        logger.error("Emailing for user %s failed.".format(user))
            else:
                try:
                    if not debug:
                        send_mail(subject='Trivia Scores Updated for Hour %d' % hour, message='Trivia scores for Hour %d have been posted. You can check your current stats at <a href="http://triviastats.com">TriviaStats.com</a>' % hour, from_email='noreply@triviastats.com', recipient_list=[user.email], fail_silently=False)
                        logger.info("Sent email to {0}".format(user.email))
                    else:
                        logger.info("Would have sent email to {0} for hour {1}".format(user.email, hour))
                except smtplib.SMTPException, e:
                    logger.error("Emailing for user %s failed.".format(user))

    def send_email(self, subscriber):
        last_hour = get_last_hour()
        top_ten = get_top_ten_teams(Settings.objects.all()[0].lasthour)
        if subscriber is None:
            return

        if subscriber.team_name:
            score = Score.objects.filter(team_name=subscriber.team_name).filter(hour=last_hour)
            if score is None:
                logger.error("Couldn't find score for Hour {0} for Team {1}".format((last_hour, subscriber.team_name)))
        else:
            logger.info("No team name. Continuing.")
        if score:
            subject = "Trivia Scores Updated for Hour %d. %s is in %d place with %d points." % (
                last_hour, subscriber.team_name, score.place, score.score)
            text_body = "Trivia scores for Hour %d have been posted. %s is in %d place with %d points. You can check your current stats at TriviaStats.com" % (last_hour, subscriber.team_name, score.place, score.score)
            html_body = "Trivia scores for Hour %d have been posted. %s is in %d place with %d points. You can check your current stats at <a href='http://triviastats.com'>TriviaStats.com</a>" % (last_hour, subscriber.team_name, score.place, score.score)
        else:
            subject = "Trivia Scores Updated for Hour %d." % (last_hour, )
            text_body = "Trivia scores for Hour %d have been posted. You can check your current stats at TriviaStats.com" % (last_hour, )
            html_body = "Trivia scores for Hour %d have been posted. You can check your current stats at <a href='http://triviastats.com'>TriviaStats.com</a>" % (last_hour, )
        ses_conn.send_email(source="TriviaStats@triviastats.com", subject=subject, body=html_body,
                            to_addresses=(subscriber.email, ), format='html',)
        logger.info("Sent email to {0}".format(subscriber.email))

    def email_update(self, ):
        for sub in EmailSubscriber.objects.all():
            self.send_email(sub)


class Scraper(object):
# During Trivia, scrapes each minute to see if a new page is up yet.
    def scraper(self, ):
        if during_trivia():
            # Scrape for new hours
            self.scrape_prev(get_current_year())
        else:
            return HttpResponse("Not during Trivia")

    # Utility function for scraping a year. Useful for setting up database with previous years.
    def scrape_prev(self, year, hour=None, force=False):
        if year is None:
            logger.error("Year is None.")
            return
        s = []
        if hour:
            hours = range(hour, hour + 1)
        elif year == 2013:
            hours = [1]
        else:
            hours = range(1, 55)
        for hr in hours:
            success = self.scrape_year_hour(year, hr, force=force)
            time.sleep(.5)
            logger.info("Success for hour {0}".format(hr))
            if success:
                s.append(hr)
        if len(s) > 0:
            sms = TwilioManager()
            email = EmailManager()
            sms.sms_notify()
            email.email_notify()

        logger.info("Success for hours: {0}".format(s))

    def spa(self, ):
        for i in range(2009, 2012):
            self.scrape_prev(i)

    def scrape_year_hour(self, yr, hr, force=False):
    # Add check right here to see if data already exists for the given year/hour


        # Trivia has a discrepancy between 02 and 2 for hours..
        if int(hr) < 10:
            if int(yr) >= 2010:
                # Add 0 to the front
                hr = "0%d" % hr
        if yr <= 2012:
            page = page_template[str(yr)] % (str(yr), str(hr))
        else:
            page = page_template[str(yr)] % (str(yr))
        logger.info("Getting page: {0}".format(page))
        try:
            p = urllib2.urlopen(page)
        except urllib2.HTTPError, e:
            # If hour 54, might need to use a special page for previous years.
            logger.info("Checking for hour 54 page. Yr: {0}, Hr: {1}".format(yr, hr))
            logger.info("Hour 54 Finals: ", hour_54_page)
            if str(yr) in hour_54_page and hr == 54:
                try:
                    page = hour_54_page[str(yr)]
                    p = urllib2.urlopen(page)
                except urllib2.HTTPError, e:
                    logger.error("Can't scrape either page 54 or final page.")
                    return False
            else:
                logger.info("No data for this hour (yet?): {0}".format(hr))
                return False
        soup = BeautifulSoup(''.join(p.read()))
        p.close()

        teams = soup.findAll('dd')
        place_score = soup.findAll('dt')
        hour = soup.findAll('h1')[0]
        hour = " ".join(hour.string.split()[5:])
        hour = self.text2int(hour.lower())
        hour = int(hour)
        print "HOUR", hour
        query = Score.objects.filter(year=int(yr)).filter(hour=int(hour))
        if len(query) != 0 and force is False:
            # print len(query)
            # for s in query:
            #     print s
            logger.info("Already in DB")
            return False
        bulk_list = []
        # Drop all teams into a list of lists:
        # 0: Team name 1: Place 2: Points
        for i in range(0, len(teams)):
            if len(place_score[i].contents) == 1:
                reg = re.findall(r'([0-9]+)', place_score[i].contents[0].replace(',', ''))
            # Happens in first occurence only
            elif len(place_score[i].contents) == 2:
                reg = re.findall(r'[0-9]{1,6}', place_score[i].contents[1].replace(',', ''))
            else:
                # Broken..
                pass

            place = reg[0]
            score = reg[1]
            # Generate teams list
            teams_list = teams[i].findAll('li')

            for j in range(0, len(teams_list)):
                # Isn't this uggggggggly?
                # Creates a list, with format noted above first for loop.
                # Replaces ugly HTML with chars.
                # db.append( (teams_list[j].string.replace('&#160;', ' ').replace('&amp;', '&').replace('&quot;', '"').replace('&nbsp;', ' '), score, place) )
                # db.append( (teams_list[j].string.replace('&#160;', ' ').replace('&amp;',
                # '&').replace('&quot;', '"').replace('&nbsp;', ' '), int(yr), int(hr),
                # place, score,) )
                name = teams_list[j].string.replace(
                    '&#160;', ' ').replace('&amp;', '&').replace('&quot;', '"').replace('&nbsp;', ' ')
                year = int(yr)
                # hour = int(hr)

                # (team_name, year, hour, place, score)
                bulk_list.append(Score(team_name=name, year=year, hour=hour, place=place, score=score))
                # print "Adding year: {0} hour: {1} team: {2} score: {3} place:
                # {4}".format(year, hour, name, score, place)
        Score.objects.bulk_create(bulk_list)
        # insert_bulk(db)
        # post_to_twitter("Hour {0} scores posted!".format(hr))
        return True

    # def calculate_changes(self, year, hour):
    #     """
    #     Should only be called after year/hour has been scraped.
    #     """
    #     hour_list = Score.objects.filter(year=2012).values_list('hour').distinct().order_by('-hour')
    #     if len(hour_list) == 0:
    #         logger.warning("Could not calculate changes for year {0} hour {1}, no scores.")
    #         return
    #     elif len(hour_list) == 1:
    #         logger.warning("First hour, ignoring.")
    #     # Find hour before hours.
    #     for past_hour in hour_list:
    #         if hour < past_hour:
    #             prev_hour = past_hour
    #             break
    #     if prev_hour is None:
    #         logger.warning("Previous hour is none for year {0} hour {1}".format(year, hour))
    #     # Get all scores for this hour and last hour.
    #     scores = Score.objects.filter(year=year).filter(hour=hour)
    #     prev_scores = Score.objects.filter(year=year).filter(hour=prev_hour)

    def text2int(self, textnum, numwords={}):
        if not numwords:
            units = [
                "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
                "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
                "sixteen", "seventeen", "eighteen", "nineteen",
                ]

            tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

            scales = ["hundred", "thousand", "million", "billion", "trillion"]

            numwords["and"] = (1, 0)
            for idx, word in enumerate(units):    numwords[word] = (1, idx)
            for idx, word in enumerate(tens):     numwords[word] = (1, idx * 10)
            for idx, word in enumerate(scales):   numwords[word] = (10 ** (idx * 3 or 2), 0)

        current = result = 0
        for word in textnum.split():
            if word not in numwords:
                raise Exception("Illegal word: " + word)

            scale, increment = numwords[word]
            current = current * scale + increment
            if scale > 100:
                result += current
                current = 0

        return result + current


class AvailableHours(models.Model):
    year = models.IntegerField()
    hour = models.IntegerField()


class Settings(models.Model):
    lastyear = models.IntegerField()
    lasthour = models.IntegerField()


class EmailSubscriber(models.Model):
    email = models.EmailField(db_index=True, unique=True)
    team_name = models.CharField(max_length=36, help_text="(optional)", blank=True, null=True)

    def __unicode__(self):
        if self.team_name:
            return "%s - %s" % (self.email, self.team_name)
        else:
            return self.email

    # def __repr__(self):
        # return self.__unicode__()


class EmailSubscriberForm(Form):
    email = EmailField()
    team_name = CharField(max_length=36, help_text="(optional)", required=False)


class EmailUnsubscribeForm(Form):
    pass


class SMSSubscriber(models.Model):
    phone_number = models.CharField(max_length=14, db_index=True, unique=True)
    team_name = models.CharField(max_length=36, blank=True, null=True)

    def __unicode__(self):
        if self.team_name:
            return "%s - %s" % (self.phone_number, self.team_name)
        else:
            return self.phone_number

    # def __repr__(self):
        # return self.__unicode__()


class SMSUnsubscribeForm(Form):
    pass


class SMSSubscriberForm(Form):
    phone_number = CharField(max_length=14)
    team_name = CharField(max_length=36, help_text="(optional)", required=False)
    # class Meta:
        # model = SMSSubscriber


class SearchForm(Form):
    search = CharField(max_length=100)


def get_current_hour():
    if not during_trivia():
        return None

    now = datetime.datetime.now()
    start_str = "%d %s %s" % (trivia_start_hour, trivia_dates[str(now.year)], now.year)
    start = datetime.datetime.strptime(start_str, "%H %B %d %Y")

    diff = now - start
    return diff.days * 24 + diff.seconds / 3600

    year = datetime.date.today().year
    trivia_start_date = trivia_dates[str(year)]
    a = str(trivia_start_date) + " " + str(year) + " " + str(trivia_start_hour)
    time.strptime(a, "%B %d %Y %H")


def get_current_year():
    return datetime.datetime.now().year

# Check


def during_trivia():
    # Simple debugging stuff
    if settings.DEBUG_DURING:
        return True

    now = datetime.datetime.now()
    start_str = "%d %s %s" % (trivia_start_hour, trivia_dates[str(now.year)], now.year)
    start = datetime.datetime.strptime(start_str, "%H %B %d %Y")
    end = start + datetime.timedelta(hours=54)

    return (start < now < end)


def get_last_hour():
    ''' Get last hour that scores were scraped '''
    last_year = get_last_year()
    return Score.objects.filter(year=last_year).values_list('hour', flat=True).distinct().order_by('-hour')[0]


def get_last_year():
    return Score.objects.values_list('year', flat=True).distinct().order_by('-year')[0]


def playing_this_year(team_name):
    ''' Find out if team is in this years competition. '''
    playing_this_year = False
    last_hour = get_last_hour()
    if last_hour is None:
        return None
    last_during_score = Score.objects.filter(
        team_name=team_name.upper()).filter(hour=last_hour).filter(year=datetime.datetime.now().year)
    if len(last_during_score) > 0:
        playing_this_year = True
    return playing_this_year


def get_start_time():
    now = datetime.datetime.now()
    return "%d %s %s" % (trivia_start_hour, trivia_dates[str(now.year)], now.year)

# Returns a list of tuples like so:
# (place (index + 1), team_name, score)
# Returns None on error


def get_top_ten_teams(year=None, hour=None):
    if year is None:
        year = get_last_year()
    if hour is None:
        hour = get_last_hour()
    place = 1

    scores = Score.objects.filter(year=year).filter(hour=hour).order_by('place')[0:10]
    return scores


def post_to_twitter(message):
    auth = twitter.OAuth(settings.TWITTER_TOKEN, settings.TWITTER_TOKEN_SECRET, settings.TWITTER_CONSUMER_KEY,
                         settings.TWITTER_CONSUMER_SECRET)
    t = twitter.Twitter(auth=auth)
    t.account.verify_credentials()
    if settings.DEBUG:
        # Don't tweet in dev.
        logger.info("Would tweet message: {0}".format(message))
    else:
        logger.info(t.statuses.update(status=message))

page_template = {'2013': 'http://90fmtrivia.org/TriviaScores%s/scorePages/results.htm', '2012': 'http://90fmtrivia.org/TriviaScores%s/scorePages/results%s.htm', '2011': 'http://90fmtrivia.org/TriviaScores%s/results%s.htm', '2010': 'http://90fmtrivia.org/scores_page/Scores%s/scores/results%s.htm', '2009': 'http://90fmtrivia.org/scores_page/Scores%s/results%s.htm'}
hour_54_page = {'2012': 'http://90fmtrivia.org/TriviaScores2012/scorePages/results.htm'}
# These are the dates of Trivia, with the year being the key, and the beginning day being the data.
trivia_dates = {"2011": "April 8", "2012": "April 20", "2013": "April 19", "2014": "April 11", "2015": "April 17",
                "2016": "April 15"}
# Start hour in 24 hour formathttp://90fmtrivia.org/scores_page/Scores2009/results2.htm
trivia_start_hour = 18
