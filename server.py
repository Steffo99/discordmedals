import datetime
from flask import Flask, redirect, session, request, render_template, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from requests_oauthlib import OAuth2Session
from uuid import uuid4
import os

app = Flask("discordmedals")
app.secret_key = os.environ["FLASK_SECRET_KEY"]
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.sqlite"
db = SQLAlchemy(app)

class Membership(db.Model):
    __tablename__ = "membership"

    permissions = db.Column(db.Integer, nullable=False)
    guild_id = db.Column(db.Integer, db.ForeignKey("guild.id"), primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)

    def __init__(self, guild_data: dict, from_user_id: int):
        self.member_id = from_user_id
        self.guild_id = guild_data["id"]
        self.permissions = guild_data["permissions"]

    def __repr__(self):
        return "<Database entry for {} membership in guild {}>".format(self.member_id, self.guild_id)


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, nullable=False)
    discriminator = db.Column(db.Integer, nullable=False)
    avatar = db.Column(db.String)
    memberships = db.relationship("Membership")

    def __init__(self, data: dict):
        self.id = data["id"]
        self.username = data["username"]
        self.discriminator = data["discriminator"]
        if "avatar" in data:
            self.avatar = data["avatar"]
        else:
            self.avatar = None

    def avatar_url(self, size=256):
        if self.avatar is None:
            return "https://discordapp.com/assets/6debd47ed13483642cf09e832ed0bc1b.png"
        return "https://cdn.discordapp.com/avatars/{}/{}.png?size={}".format(self.id, self.avatar, size)

    def __str__(self):
        return "{}#{}".format(self.username, self.discriminator)

    def __repr__(self):
        return "<Database entry for Discord user {}>".format(self.id)

    def mention(self):
        return "<@{}>".format(self.id)


class Guild(db.Model):
    __tablename__ = "guild"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    icon = db.Column(db.String)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    owner = db.relationship("User", backref="owns")
    members = db.relationship("Membership")

    def __init__(self, guild_data: dict, from_user_id: int):
        self.id = guild_data["id"]
        self.name = guild_data["name"]
        if "icon" is not None:
            self.icon = guild_data["icon"]
        else:
            self.icon = None
        if guild_data["owner"]:
            self.owner_id = from_user_id

    def icon_url(self, size=256):
        # Size can be up to 512px...?
        if self.icon is None:
            return "https://discordapp.com/assets/6debd47ed13483642cf09e832ed0bc1b.png"
        return "https://cdn.discordapp.com/icons/{}/{}.png?size={}".format(self.id, self.icon, size)

    def __str__(self):
        return self.name

    def __repr__(self):
        return "<Database entry for Discord guild {}>".format(self.id)


class Medal(db.Model):
    __tablename__ = "medal"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.String)
    icon = db.Column(db.String)
    tier = db.Column(db.String, nullable=False)
    token = db.Column(db.String, nullable=False)
    guild_id = db.Column(db.Integer, db.ForeignKey("guild.id"))
    guild = db.relationship("Guild", backref="medals")

    def __init__(self, name: str, description: str, icon: str, tier: str, guild_id: int):
        self.name = name
        self.description = description
        self.icon = icon
        self.tier = tier
        self.guild_id = guild_id
        self.token = uuid4().hex

    def __str__(self):
        return self.name

    def __repr__(self):
        return "<Database entry for Medal {}>".format(self.id)


class Award(db.Model):
    __tablename__ = "award"

    award_id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    medal_id = db.Column(db.Integer, db.ForeignKey("medal.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    medal = db.relationship("Medal", backref="awards")
    user = db.relationship("User", backref="awards")

    def __init__(self, medal_id: int, user_id: int, date):
        self.date = date
        self.medal_id = medal_id
        self.user_id = user_id

    def __repr__(self):
        return "<Database entry for Medal {} awarded to {} on {}>".format(self.medal_id, self.user_id, self.date)


if not os.path.exists(os.path.dirname(__file__).join("database.sqlite")):
    db.create_all()


oauth2_client_id = os.environ["DISCORD_OAUTH_CLIENT_ID"]
oauth2_client_secret = os.environ["DISCORD_OAUTH_CLIENT_SECRET"]
oauth2_redirect = os.environ["BASE_DOMAIN_NAME"] + "/loggedin"
oauth2_token_url = "https://discordapp.com/api/oauth2/token"


def update_token(token):
    session["oauth2_token"] = token


def make_session(token=None, state=None, scope=None):
    return OAuth2Session(client_id=oauth2_client_id,
                         token=token,
                         state=state,
                         scope=scope,
                         redirect_uri=oauth2_redirect,
                         auto_refresh_kwargs={
                             'client_id': oauth2_client_id,
                             'client_secret': oauth2_client_secret,
                         },
                         auto_refresh_url=oauth2_token_url,
                         token_updater=update_token)

def count_awards_by_tier(awards_joined_with_medals: list):
    bronze = 0
    silver = 0
    gold = 0
    for award in awards_joined_with_medals:
        if award.medal.tier == "bronze":
            bronze += 1
        elif award.medal.tier == "silver":
            silver += 1
        elif award.medal.tier == "gold":
            gold += 1
    return bronze, silver, gold


def count_medals_by_tier(medals: list):
    bronze = 0
    silver = 0
    gold = 0
    for medal in medals:
        if medal.tier == "bronze":
            bronze += 1
        elif medal.tier == "silver":
            silver += 1
        elif medal.tier == "gold":
            gold += 1
    return bronze, silver, gold


@app.route("/")
def page_home():
    user_id = session.get("user_id")
    if user_id is None:
        return render_template("base.htm.j2", user=None)
    return redirect("/user/{}".format(user_id))


@app.route("/guild/<int:guild_id>")
def page_guild(guild_id):
    guild = Guild.query.filter_by(id=guild_id).first()
    if guild is None:
        abort(404)
    medals = Medal.query.filter_by(guild_id=guild_id).all()
    members = User.query.join(Membership).filter_by(guild_id=guild_id).all()
    user_id = session.get("user_id")
    if user_id is None:
        user = None
    else:
        user = User.query.filter_by(id=session["user_id"]).first()
    bronze, silver, gold = count_medals_by_tier(medals)
    return render_template("guild.htm.j2", user=user, medals=medals, members=members, guild=guild, bronze=bronze, silver=silver, gold=gold)


@app.route("/guild/<int:guild_id>/new", methods=["GET", "POST"])
def page_newmedal(guild_id):
    guild = Guild.query.filter_by(id=guild_id).first()
    if guild is None:
        abort(404)
    user_id = session.get("user_id")
    if user_id is None or int(user_id) != int(guild.owner_id):
        abort(403)
    if request.method == "GET":
        user = User.query.filter_by(id=user_id).first()
        return render_template("newmedal.htm.j2", user=user, target="new")
    elif request.method == "POST":
        name = request.form["name"]
        if len(name) > 128:
            abort(400)
        description = request.form["description"]
        if len(description) > 512:
            abort(400)
        icon = request.form["icon"]
        # TODO: possibile injection qui
        tier = request.form["tier"]
        if tier != "bronze" and tier != "silver" and tier != "gold":
            abort(400)
        medal = Medal(name=name, description=description, icon=icon, tier=tier, guild_id=guild_id)
        db.session.add(medal)
        db.session.commit()
        return redirect("/guild/{}".format(guild_id))


@app.route("/medal/<int:medal_id>")
def page_medal(medal_id):
    medal = Medal.query.filter_by(id=medal_id).first()
    awards = Award.query.filter_by(medal_id=medal_id).join(User).all()
    if medal is None:
        abort(404)
    user_id = session.get("user_id")
    if user_id is None:
        user = None
    else:
        user = User.query.filter_by(id=session["user_id"]).first()
    return render_template("medal.htm.j2", user=user, medal=medal, awards=awards)


@app.route("/medal/<int:medal_id>/edit", methods=["GET", "POST"])
def page_editmedal(medal_id):
    medal = Medal.query.filter_by(id=medal_id).first()
    if medal is None:
        abort(404)
    user_id = session.get("user_id")
    if user_id is None or int(user_id) != int(medal.guild.owner_id):
        abort(403)
    if request.method == "GET":
        user = User.query.filter_by(id=user_id).first()
        return render_template("newmedal.htm.j2", user=user, medal=medal, target="edit")
    elif request.method == "POST":
        name = request.form["name"]
        if len(name) > 128:
            abort(400)
        description = request.form["description"]
        if len(description) > 512:
            abort(400)
        icon = request.form["icon"]
        # TODO: possibile injection qui
        tier = request.form["tier"]
        if tier != "bronze" and tier != "silver" and tier != "gold":
            abort(400)
        medal.name = name
        medal.description = description
        medal.icon = icon
        medal.tier = tier
        db.session.commit()
        return redirect("/guild/{}".format(medal.guild_id))


@app.route("/user/<int:user_id>")
def page_user(user_id):
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        abort(404)
    guilds = Guild.query.join(Membership).filter_by(member_id=user.id).all()
    award_groups = list()
    for guild in guilds:
        awards = Award.query.filter_by(user_id=user.id).join(Medal).filter_by(guild_id=guild.id).all()
        award_groups.append(awards)
    logged_user_id = session.get("user_id")
    if logged_user_id is None:
        logged_user = None
    else:
        logged_user = User.query.filter_by(id=logged_user_id).first()
    return render_template("user.htm.j2", user=logged_user, queried_user=user, guilds=enumerate(guilds), award_groups=award_groups)


@app.route("/api/awardmedal")
def api_awardmedal():
    token = request.args.get("token")
    if token is None:
        return jsonify({
            "success": False,
            "error": "Missing medal token"
        })
    medal = Medal.query.filter_by(token=token).first()
    if medal is None:
        return jsonify({
            "success": False,
            "error": "Invalid medal token"
        })
    user_id = request.args.get("user")
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        return jsonify({
            "success": False,
            "error": "User not found"
        })
    unique = request.args.get("unique", False)
    if unique:
        queried_medal = Award.query.filter_by(medal_id=medal.id, user_id=user.id).first()
        if queried_medal:
            return jsonify({
                "success": False,
                "error": "User already owns the medal"
            })
    award = Award(medal_id=medal.id, user_id=user.id, date=datetime.datetime.now())
    db.session.add(award)
    db.session.commit()
    return jsonify({
        "success": True,
        "award_id": award.award_id
    })


@app.route("/api/revokeaward")
def api_revokeaward():
    token = request.args.get("token")
    if token is None:
        return jsonify({
            "success": False,
            "error": "Missing medal token"
        })
    medal = Medal.query.filter_by(token=token).first()
    if medal is None:
        return jsonify({
            "success": False,
            "error": "Invalid medal token"
        })
    award_id = request.args.get("award")
    if award_id is None:
        return jsonify({
            "success": False,
            "error": "Missing award id"
        })
    award = Award.query.filter_by(award_id=award_id).first()
    if award is None:
        return jsonify({
            "success": False,
            "error": "Invalid award id"
        })
    db.session.delete(award)
    db.session.commit()
    return jsonify({
        "success": True
    })


@app.route("/api/regentoken")
def api_revoketoken():
    token = request.args.get("token")
    if token is None:
        return jsonify({
            "success": False,
            "error": "Missing medal token"
        })
    medal = Medal.query.filter_by(token=token).first()
    if medal is None:
        return jsonify({
            "success": False,
            "error": "Invalid medal token"
        })
    medal.token = uuid4().hex
    db.session.commit()
    return jsonify({
        "success": True,
        "new_token": medal.token
    })


@app.route("/login")
def page_login():
    scope = ["identify", "guilds"]
    oauth = make_session(scope=scope)
    auth_url, state = oauth.authorization_url("https://discordapp.com/api/oauth2/authorize")
    session["oauth2_state"] = state
    return redirect(auth_url)


@app.route("/loggedin")
def page_loggedin():
    if session.get("oauth2_state") is None:
        return redirect("/")
    if request.values.get("error") is not None:
        return redirect("/")
    oauth = make_session(state=session["oauth2_state"])
    session["oauth2_token"] = oauth.fetch_token(oauth2_token_url, client_secret=oauth2_client_secret, authorization_response=request.url)
    # Check if the user already exists in the database
    oauth = make_session(token=session["oauth2_token"])
    userdata = oauth.get("https://discordapp.com/api/users/@me").json()
    userquery = User.query.filter_by(id=userdata["id"]).first()
    # If it doesn't exist, create a new row containing his info
    if userquery is None:
        # Add user data to the database
        newuser = User(userdata)
        db.session.add(newuser)
    else:
        userquery.__init__(userdata)
    # Update guilds data
    guildsdata = oauth.get("https://discordapp.com/api/users/@me/guilds").json()
    # Add new guild
    for guilddata in guildsdata:
        # Check if the guild exists
        guildquery = Guild.query.filter_by(id=guilddata["id"]).first()
        if guildquery is None:
            # Add guild data to the database
            newguild = Guild(guilddata, userdata["id"])
            db.session.add(newguild)
        else:
            # Update guild data
            guildquery.__init__(guilddata, userdata["id"])
        # Check / update the membership
        membership = Membership.query.filter_by(guild_id=guilddata["id"], member_id=userdata["id"]).first()
        if membership is None:
            membership = Membership(guilddata, userdata["id"])
            db.session.add(membership)
        else:
            # Update membership data
            membership.__init__(guilddata, userdata["id"])
    db.session.commit()
    # TODO: remove left guilds?
    # Save the userid in the session data
    session["user_id"] = userdata["id"]
    # Go back to the home page
    return redirect("/")


@app.route("/logout")
def page_logout():
    session["oauth2_token"] = None
    session["oauth2_state"] = None
    session["user_id"] = None
    return redirect("/")


if __name__ == "__main__":
    app.run()
