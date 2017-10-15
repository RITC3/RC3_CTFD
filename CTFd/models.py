from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import DatabaseError
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import union_all

from socket import inet_aton, inet_ntoa
from struct import unpack, pack, error as struct_error
from passlib.hash import bcrypt_sha256

import datetime
import hashlib
import json


def sha512(string):
    return hashlib.sha512(string).hexdigest()


def ip2long(ip):
    return unpack('!i', inet_aton(ip))[0]


def long2ip(ip_int):
    try:
        return inet_ntoa(pack('!i', ip_int))
    except struct_error:
        # Backwards compatibility with old CTFd databases
        return inet_ntoa(pack('!I', ip_int))


def get_standings(admin=False, count=None):
    standings = []
    q = db.session.query(Solves).count()
    if( q > 0):
        score = db.func.sum(Challenges.value).label('score')
        date = db.func.max(Solves.date).label('date')
        scores = db.session.query(Solves.userid.label('userid'), score, date).join(Challenges).group_by(Solves.userid)
        print(score)
        awards = db.session.query(Awards.userid.label('userid'), db.func.sum(Awards.value).label('score'),
                                  db.func.max(Awards.date).label('date')) \
            .group_by(Awards.userid)
        results = union_all(scores, awards).alias('results')
        sumscores = db.session.query(results.columns.userid, db.func.sum(results.columns.score).label('score'),
                                     db.func.max(results.columns.date).label('date')) \
            .group_by(results.columns.userid).subquery()
        if admin:
            db.session.query(Users.teamid.label('teamid'),
                                               Teams.name.label('name'),
                                               Teams.banned,
                                               db.func.sum(sumscores.columns.score).label('score')) \
                .join(sumscores, Users.id == sumscores.columns.userid) \
                .join(Teams, Users.teamid == Teams.id) \
                .filter(Users.banned == False) \
                .order_by(score.desc(), sumscores.columns.date) \
                .group_by(Teams.name)
        else:
            standings_query = db.session.query(Users.teamid.label('teamid'),
                                               Teams.name.label('name'),
                                               db.func.sum(sumscores.columns.score).label('score')) \
                .join(sumscores, Users.id == sumscores.columns.userid) \
                .join(Teams, Users.teamid == Teams.id) \
                .filter(Teams.banned == False) \
                .order_by(score.desc(), sumscores.columns.date) \
                .group_by(Teams.name)
        if count is None:
            standings = standings_query.all()
        else:
            standings = standings_query.limit(count).all()
        db.session.close()
    return standings

db = SQLAlchemy()


class Pages(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    route = db.Column(db.String(80), unique=True)
    html = db.Column(db.Text)

    def __init__(self, route, html):
        self.route = route
        self.html = html

    def __repr__(self):
        return "<Pages {0} for challenge {1}>".format(self.tag, self.chal)


class Containers(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    buildfile = db.Column(db.Text)

    def __init__(self, name, buildfile):
        self.name = name
        self.buildfile = buildfile

    def __repr__(self):
        return "<Container ID:(0) {1}>".format(self.id, self.name)


class Challenges(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    description = db.Column(db.Text)
    value = db.Column(db.Integer)
    category = db.Column(db.String(80))
    flags = db.Column(db.Text)
    hidden = db.Column(db.Boolean)

    def __init__(self, name, description, value, category, flags):
        self.name = name
        self.description = description
        self.value = value
        self.category = category
        self.flags = json.dumps(flags)

    def __repr__(self):
        return '<chal %r>' % self.name


class Awards(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    userid = db.Column(db.Integer, db.ForeignKey('users.id'))
    name = db.Column(db.String(80))
    description = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    value = db.Column(db.Integer)
    category = db.Column(db.String(80))
    icon = db.Column(db.Text)

    def __init__(self, userid, name, value):
        self.userid = userid
        self.name = name
        self.value = value

    def __repr__(self):
        return '<award %r>' % self.name


class Tags(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chal = db.Column(db.Integer, db.ForeignKey('challenges.id'))
    tag = db.Column(db.String(80))

    def __init__(self, chal, tag):
        self.chal = chal
        self.tag = tag

    def __repr__(self):
        return "<Tag {0} for challenge {1}>".format(self.tag, self.chal)


class Files(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chal = db.Column(db.Integer, db.ForeignKey('challenges.id'))
    location = db.Column(db.Text)

    def __init__(self, chal, location):
        self.chal = chal
        self.location = location

    def __repr__(self):
        return "<File {0} for challenge {1}>".format(self.location, self.chal)


class Keys(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chal = db.Column(db.Integer, db.ForeignKey('challenges.id'))
    key_type = db.Column(db.Integer)
    flag = db.Column(db.Text)

    def __init__(self, chal, flag, key_type):
        self.chal = chal
        self.flag = flag
        self.key_type = key_type

    def __repr__(self):
        return self.flag


class Teams(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True)
    captain = db.Column(db.Integer, db.ForeignKey('users.id'))
    website = db.Column(db.String(128))
    affiliation = db.Column(db.String(128))
    country = db.Column(db.String(32))
    bracket = db.Column(db.String(32))
    banned = db.Column(db.Boolean, default=False)

    def __init__(self, name, captain):
        self.name = name
        self.captain = captain

    def __repr__(self):
        return '<Team %r>' % self.name

    def score(self):
        users = Users.query.filter_by(teamid=self.id).all()
        return sum(user.score() for user in users)

    def place(self):
        standings = get_standings()
        # http://codegolf.stackexchange.com/a/4712
        try:
            i = [y[0] for y in standings].index(self.id) + 1
            k = i % 10
            print i, k
            return "%d%s" % (i, "tsnrhtdd"[(i / 10 % 10 != 1) * (k < 4) * k::4])
        except ValueError:
            return 0


class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True)
    email = db.Column(db.String(128), unique=True)
    password = db.Column(db.String(128))
    banned = db.Column(db.Boolean, default=False)
    share = db.Column(db.Boolean, default=True)
    verified = db.Column(db.Boolean, default=False)
    admin = db.Column(db.Boolean, default=False)
    joined = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    teamid = db.Column(db.Integer, db.ForeignKey('teams.id'))

    def __init__(self, name, email, password):
        self.name = name
        self.email = email
        self.password = bcrypt_sha256.encrypt(str(password))

    def __repr__(self):
        return '<User %r>' % self.name

    def score(self):
        score = db.func.sum(Challenges.value).label('score')
        team = db.session.query(Solves.userid, score).join(Users).join(Challenges).filter(Users.banned == False, Users.id == self.id).group_by(Solves.userid).first()
        award_score = db.func.sum(Awards.value).label('award_score')
        award = db.session.query(award_score).filter_by(userid=self.id).first()
        if team:
            return int(team.score or 0) + int(award.award_score or 0)
        else:
            return 0

    def place(self):
        score = db.func.sum(Challenges.value).label('score')
        quickest = db.func.max(Solves.date).label('quickest')
        teams = db.session.query(Solves.userid).join(Users).join(Challenges).filter(Users.banned == False).group_by(Solves.userid).order_by(score.desc(), quickest).all()
        #http://codegolf.stackexchange.com/a/4712
        try:
            i = teams.index((self.id,)) + 1
            k = i % 10
            return "%d%s" % (i, "tsnrhtdd"[(i / 10 % 10 != 1) * (k < 4) * k::4])
        except ValueError:
            return 0


class Solves(db.Model):
    __table_args__ = (db.UniqueConstraint('chalid', 'userid'), {})
    id = db.Column(db.Integer, primary_key=True)
    chalid = db.Column(db.Integer, db.ForeignKey('challenges.id'))
    userid = db.Column(db.Integer, db.ForeignKey('users.id'))
    ip = db.Column(db.Integer)
    flag = db.Column(db.Text)
    date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    user = db.relationship('Users', foreign_keys="Solves.userid", lazy='joined')
    chal = db.relationship('Challenges', foreign_keys="Solves.chalid", lazy='joined')
    # value = db.Column(db.Integer)

    def __init__(self, chalid, userid, ip, flag):
        self.ip = ip2long(ip)
        self.chalid = chalid
        self.userid = userid
        self.flag = flag
        # self.value = value

    def __repr__(self):
        return '<solves %r>' % self.chal


class WrongKeys(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chalid = db.Column(db.Integer, db.ForeignKey('challenges.id'))
    userid = db.Column(db.Integer, db.ForeignKey('users.id'))
    date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    flag = db.Column(db.Text)
    chal = db.relationship('Challenges', foreign_keys="WrongKeys.chalid", lazy='joined')

    def __init__(self, userid, chalid, flag):
        self.userid = userid
        self.chalid = chalid
        self.flag = flag

    def __repr__(self):
        return '<wrong %r>' % self.flag


class Tracking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.BigInteger)
    user = db.Column(db.Integer, db.ForeignKey('users.id'))
    date = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def __init__(self, ip, user):
        self.ip = ip2long(ip)
        self.user = user

    def __repr__(self):
        return '<ip %r>' % self.user


class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.Text)
    value = db.Column(db.Text)

    def __init__(self, key, value):
        self.key = key
        self.value = value
