from flask import current_app as app, session, render_template, jsonify, Blueprint, redirect, url_for, request
from CTFd.utils import unix_time, authed, get_config
from CTFd.models import db, Users, Solves, Awards, Challenges, Teams, get_standings

scoreboard = Blueprint('scoreboard', __name__)

# def get_standings(admin=False, count=None):
#     score = db.func.sum(Challenges.value).label('score')
#     date = db.func.max(Solves.date).label('date')
#     scores = db.session.query(Solves.userid.label('userid'), score, date).join(Challenges).group_by(Solves.userid)
#     awards = db.session.query(Awards.userid.label('userid'), db.func.sum(Awards.value).label('score'), db.func.max(Awards.date).label('date')) \
#         .group_by(Awards.userid)
#     results = union_all(scores, awards).alias('results')
#     sumscores = db.session.query(results.columns.userid, db.func.sum(results.columns.score).label('score'), db.func.max(results.columns.date).label('date')) \
#         .group_by(results.columns.userid).subquery()
#     if admin:
#         standings_query = db.session.query(Users.id.label('userid'), Users.name.label('name'), Users.banned, sumscores.columns.score) \
#             .join(sumscores, Users.id == sumscores.columns.userid) \
#             .order_by(sumscores.columns.score.desc(), sumscores.columns.date)
#     else:
#         standings_query = db.session.query(Users.id.label('userid'), Users.name.label('name'), sumscores.columns.score) \
#             .join(sumscores, Users.id == sumscores.columns.userid) \
#             .filter(Users.banned == False) \
#             .order_by(sumscores.columns.score.desc(), sumscores.columns.date)
#     if count is None:
#         standings = standings_query.all()
#     else:
#         standings = standings_query.limit(count).all()
#     print standings
#     db.session.close()
#     return standings


@scoreboard.route('/scoreboard')
def scoreboard_view():
    if get_config('view_scoreboard_if_authed') and not authed():
        return redirect(url_for('auth.login', next=request.path))
    standings = get_standings()
    return render_template('scoreboard.html', teams=standings)


@scoreboard.route('/scores')
def scores():
    if get_config('view_scoreboard_if_authed') and not authed():
        return redirect(url_for('auth.login', next=request.path))
    standings = get_standings()
    json = {'standings':[]}
    for i, x in enumerate(standings):
        json['standings'].append({'pos':i+1, 'id':x.userid, 'team':x.name,'score':int(x.score)})
    return jsonify(json)


@scoreboard.route('/top/<int:count>')
def topteams(count):
    if get_config('view_scoreboard_if_authed') and not authed():
        return redirect(url_for('auth.login', next=request.path))
    if count > 20 or count < 0:
        count = 10

    json = {'scores':{}}
    standings = get_standings(count=count)

    for team in standings:
        user_ids = [u.id for u in Users.query.with_entities(Users.id).filter_by(teamid=team.teamid)]
        solves = Solves.query.filter(Solves.userid.in_(user_ids)).all()
        awards = Awards.query.filter(Awards.userid.in_(user_ids)).all()
        json['scores'][team.name] = []
        scores = []
        for x in solves:
            json['scores'][team.name].append({
                'chal': x.chalid,
                'team': team.teamid,
                'value': x.chal.value,
                'time': unix_time(x.date)
            })
        for award in awards:
            json['scores'][team.name].append({
                'chal': None,
                'team': team.teamid,
                'value': award.value,
                'time': unix_time(award.date)
            })
        json['scores'][team.name] = sorted(json['scores'][team.name], key=lambda k: k['time'])
    return jsonify(json)
