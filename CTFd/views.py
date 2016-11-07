from flask import current_app as app, render_template, render_template_string, request, redirect, abort, jsonify, json as json_mod, url_for, session, Blueprint, Response
from CTFd.utils import authed, ip2long, long2ip, is_setup, validate_url, get_config, set_config, sha512, get_ip, cache, is_on_team
from CTFd.models import db, Users, Solves, Awards, Challenges, WrongKeys, Keys, Tags, Files, Tracking, Pages, Config, Teams

from jinja2.exceptions import TemplateNotFound
from passlib.hash import bcrypt_sha256
from collections import OrderedDict
from itsdangerous import TimedSerializer, BadTimeSignature, Signer, BadSignature

import logging
import os
import re
import sys
import json
import os
import datetime
import urllib

views = Blueprint('views', __name__)


@views.before_request
def redirect_setup():
    if request.path.startswith("/static"):
        return
    if not is_setup() and request.path != "/setup":
        return redirect(url_for('views.setup'))


@views.route('/setup', methods=['GET', 'POST'])
def setup():
    # with app.app_context():
        # admin = Teams.query.filter_by(admin=True).first()

    if not is_setup():
        if not session.get('nonce'):
            session['nonce'] = sha512(os.urandom(10))
        if request.method == 'POST':
            ctf_name = request.form['ctf_name']
            ctf_name = set_config('ctf_name', ctf_name)

            ## CSS
            css = set_config('start', '')

            ## Admin user
            name = request.form['name']
            email = request.form['email']
            password = request.form['password']
            admin = Users(name, email, password)
            admin.admin = True
            admin.banned = True

            ## Index page
            page = Pages('index', """<div class="container main-container">
    <img class="logo" src="{0}/static/original/img/logo.png" />
    <h3 class="text-center">
        Welcome to a cool CTF framework written by <a href="https://github.com/ColdHeat">Kevin Chung</a> of <a href="https://github.com/isislab">@isislab</a>
    </h3>

    <h4 class="text-center">
        <a href="{0}/admin">Click here</a> to login and setup your CTF
    </h4>
</div>""".format(request.script_root))

            #max attempts per challenge
            max_tries = set_config("max_tries", 0)

            ## Team size limit
            team_limit = set_config('team_limit', 5)

            ## Start time
            start = set_config('start', None)
            end = set_config('end', None)

            ## Challenges cannot be viewed by unregistered users
            view_challenges_unregistered = set_config('view_challenges_unregistered', None)

            ## Allow/Disallow registration
            prevent_registration = set_config('prevent_registration', None)

            ## Verify emails
            verify_emails = set_config('verify_emails', None)

            mail_server = set_config('mail_server', None)
            mail_port = set_config('mail_port', None)
            mail_tls = set_config('mail_tls', None)
            mail_ssl = set_config('mail_ssl', None)
            mail_username = set_config('mail_username', None)
            mail_password = set_config('mail_password', None)

            setup = set_config('setup', True)

            db.session.add(page)
            db.session.add(admin)
            db.session.commit()
            db.session.close()
            app.setup = False
            with app.app_context():
                cache.clear()
            return redirect(url_for('views.static_html'))
        return render_template('setup.html', nonce=session.get('nonce'))
    return redirect(url_for('views.static_html'))


# Custom CSS handler
@views.route('/static/user.css')
def custom_css():
    return Response(get_config("css"), mimetype='text/css')


# Static HTML files
@views.route("/", defaults={'template': 'index'})
@views.route("/<template>")
def static_html(template):
    try:
        return render_template('%s.html' % template)
    except TemplateNotFound:
        page = Pages.query.filter_by(route=template).first()
        if page:
            return render_template('page.html', content=page.html)
        else:
            abort(404)


@views.route('/teams', defaults={'page':'1'})
@views.route('/teams/<page>')
def teams(page):
    page = abs(int(page))
    results_per_page = 50
    page_start = results_per_page * ( page - 1 )
    page_end = results_per_page * ( page - 1 ) + results_per_page

    if get_config('verify_emails'):
        count = Teams.query.count()
        teams = Teams.query.slice(page_start, page_end).all()
    else:
        count = Teams.query.count()
        teams = Teams.query.slice(page_start, page_end).all()
    pages = int(count / results_per_page) + (count % results_per_page > 0)
    return render_template('teams.html', teams=teams, team_pages=pages, curr_page=page)


@views.route('/user/<userid>', methods=['GET', 'POST'])
def user_view(userid):
    if get_config('view_scoreboard_if_authed') and not authed():
        return redirect(url_for('auth.login', next=request.path))
    user = Users.query.filter_by(id=userid).first_or_404()
    solves = Solves.query.filter_by(userid=userid)
    awards = Awards.query.filter_by(userid=userid).all()
    score = user.score()
    place = user.place()
    db.session.close()

    if request.method == 'GET':
        return render_template('user.html', solves=solves, awards=awards, team=user, score=score, place=place)
    elif request.method == 'POST':
        json = {'solves':[]}
        for x in solves:
            json['solves'].append({'id':x.id, 'chal':x.chalid, 'team':x.userid})
        return jsonify(json)


@views.route('/user/<userid>/remove', methods=['POST'])
def user_remove(userid):
    if authed() and is_on_team():
        current_user = Users.query.filter_by(id=session.get('id')).first()
        target_user = Users.query.filter_by(id=userid).first()
        team = Teams.query.filter_by(id=current_user.teamid).first()
        if team.captain == target_user.id:
            users = Users.query.filter_by(teamid=team.id)
            for user in users:
                user.teamid = None
            db.session.delete(team)
            db.session.commit()
            db.session.close()
            return "-1"
        if team.captain == current_user.id:
            target_user.teamid = None
            db.session.commit()
            db.session.close()
            return "1"
        return "0"
    else:
        return redirect(url_for('auth.login'))


@views.route('/team/<teamid>', methods=['GET', 'POST'])
def team_view(teamid):
    if get_config('view_scoreboard_if_authed') and not authed():
        return redirect(url_for('auth.login', next=request.path))
    team = Teams.query.filter_by(id=teamid).first_or_404()
    users = Users.query.filter_by(teamid=teamid).all()
    user_ids = [u.id for u in users]

    solves = Solves.query.filter(Solves.userid.in_(user_ids))

    db.session.close()

    if request.method == 'GET':
        return render_template('team.html', team=team, users=users, solves=solves)
    # elif request.method == 'POST':
    #     json = {'solves': []}
    #     for x in solves:
    #         json['solves'].append({'id': x.id, 'chal': x.chalid, 'team': x.userid})
    #     return jsonify(json)


@views.route('/team', methods=['POST', 'GET'])
def team_management():
    if authed():
        user = Users.query.filter_by(id=session.get('id')).first_or_404()
        if user.teamid: ## Already has team
            s = Signer(app.config['SECRET_KEY'])
            team = Teams.query.filter_by(id=user.teamid).first_or_404()
            users = Users.query.filter_by(teamid=user.teamid)
            secret = urllib.quote_plus(s.sign(str(team.id)).encode('base64'))
            if request.method == "POST":
                errors = []
                if team.captain == user.id:
                    website = request.form.get('website')
                    affiliation = request.form.get('affiliation')
                    country = request.form.get('country')

                    if website.strip() and not validate_url(website):
                        errors.append("That doesn't look like a valid URL")

                    team.website = website
                    team.affiliation = affiliation
                    team.country = country
                else:
                    errors.append('Only team captains can change this information.')
                if errors:
                    return render_template('view_team.html', team=team, users=users, secret=secret, errors=errors)
                db.session.commit()
                db.session.close()
                return redirect(url_for('views.team_management'))
            else:
                captain = False
                if team.captain == user.id:
                    captain = True
                return render_template('view_team.html', team=team, users=users, secret=secret, captain=captain)
        else: ## Needs a team
            if request.method == "POST":
                name = request.form.get('name')
                captain = session.get('id')
                team = Teams.query.filter_by(name=name).first()
                errors = []
                if team:
                    errors.append('That team name is already taken')

                t = Teams(name, captain)

                if errors:
                    return render_template('create_team.html', errors=errors, team=t)

                db.session.add(t)
                db.session.flush()

                user.teamid = t.id
                db.session.commit()
                db.session.close()
                return redirect(url_for('views.team_management'))
            else:
                return render_template('create_team.html')
    else:
        return redirect(url_for('auth.login'))


@views.route('/join/<team_link>', methods=['POST', 'GET'])
def join_team(team_link):
    errors = []
    if authed():
        user = Users.query.filter_by(id=session.get('id')).first_or_404()
        s = Signer(app.config['SECRET_KEY'])
        team_id = s.unsign(urllib.unquote_plus(team_link.decode('base64')))
        team = Teams.query.filter_by(id=team_id).first_or_404()
        user_ids = [u.id for u in Users.query.with_entities(Users.id).filter_by(teamid=team.id)]
        team_captain = Teams.query.filter_by(captain=user.id).first()
        print team_captain
        if request.method == "POST":
            if len(user_ids) >= get_config('team_limit'):
                errors.append('This team is full')
            if team_captain:
                errors.append("You are captain of another team, you can't join another team")
            if errors:
                return render_template('join_team.html', team=team, errors=errors)
            user.teamid = int(team.id)
            db.session.commit()
            db.session.close()
            return redirect(url_for('views.team_management'))
        else:
            if len(user_ids) >= get_config('team_limit'):
                errors.append('This team is full')
            if user.teamid:
                errors.append('You are already on a team. <br>Joining a new team will take all your solves with you.')
            if team_captain:
                errors.append("You are captain of another team, you can't join another team")
            return render_template('join_team.html', team=team, errors=errors)
    else:
        return redirect(url_for('auth.login', next=request.path))


@views.route('/profile', methods=['POST', 'GET'])
def profile():
    if authed():
        if request.method == "POST":
            errors = []

            name = request.form.get('name')
            email = request.form.get('email')
            try:
                share = bool(request.form.get('share', None))
            except (ValueError, TypeError):
                share = None

            user = Users.query.filter_by(id=session['id']).first()

            if not get_config('prevent_name_change'):
                names = Users.query.filter_by(name=name).first()
                name_len = len(request.form['name']) == 0

            emails = Users.query.filter_by(email=email).first()
            valid_email = re.match(r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)", email)

            if ('password' in request.form.keys() and not len(request.form['password']) == 0) and \
                    (not bcrypt_sha256.verify(request.form.get('confirm').strip(), user.password)):
                errors.append("Your old password doesn't match what we have.")
            if not valid_email:
                errors.append("That email doesn't look right")
            if not get_config('prevent_name_change') and names and name!=session['username']:
                errors.append('That team name is already taken')
            if emails and emails.id != session['id']:
                errors.append('That email has already been used')
            if not get_config('prevent_name_change') and name_len:
                errors.append('Pick a longer team name')
            # if website.strip() and not validate_url(website):
            #     errors.append("That doesn't look like a valid URL")

            if len(errors) > 0:
                return render_template('profile.html', name=name, email=email, share=share, errors=errors)
            else:
                user = Users.query.filter_by(id=session['id']).first()
                if not get_config('prevent_name_change'):
                    user.name = name
                if user.email != email.lower():
                    user.email = email.lower()
                    if get_config('verify_emails'):
                        user.verified = False
                session['username'] = user.name

                if 'password' in request.form.keys() and not len(request.form['password']) == 0:
                    user.password = bcrypt_sha256.encrypt(request.form.get('password'))
                user.share = share
                db.session.commit()
                db.session.close()
                return redirect(url_for('views.profile'))
        else:
            user = Users.query.filter_by(id=session['id']).first()
            name = user.name
            email = user.email
            share = user.share
            # website = user.website
            # affiliation = user.affiliation
            # country = user.country
            prevent_name_change = get_config('prevent_name_change')
            confirm_email = get_config('verify_emails') and not user.verified
            return render_template('profile.html', name=name, email=email, share=share, prevent_name_change=prevent_name_change, confirm_email=confirm_email)
    else:
        return redirect(url_for('auth.login'))
