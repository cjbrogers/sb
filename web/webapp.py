from flask import Flask, flash, redirect, render_template, request, session, abort, url_for
from app import NHL_Info
import pandas as pd
import pymysql
from sqlalchemy import create_engine
import myql
from yahoo_oauth import OAuth1
from myql import MYQL
import xml.etree.ElementTree as ET

app = Flask(__name__)

# only consumer_key and consumer_secret are required.
oauth = OAuth1(None, None, from_file='../oauth1.json')
guid = oauth.guid
consumer_key = oauth.consumer_key
consumer_secret = oauth.consumer_secret
session_handle = oauth.session_handle
access_token_secret = oauth.access_token_secret
yql = MYQL(format='xml', oauth=oauth)
league_key = 'nhl.l.22070'
NSMAP = {'yh': 'http://fantasysports.yahooapis.com/fantasy/v2/base.rng'}


def get_current_week():
    current_week = yql.raw_query(
        'select current_week from fantasysports.leagues.standings where league_key in ("' + league_key + '")')
    week_tree = ET.fromstring(current_week.text)
    week = None
    for data in week_tree.findall('.//yh:league', namespaces=NSMAP):
        week = int(data.find('.//yh:current_week', namespaces=NSMAP).text)
        break
    if week:
        return week


@app.route("/")
def index():
    current_week = get_current_week()
    week_info = NHL_Info(current_week)
    df_league = week_info.df_league
    return render_template('index.html', df_league=df_league, table=df_league.to_html(classes='table table-bordered table-striped table-hover league'), title='League Standings')


@app.route("/tables/", methods=['POST'])
def show_tables():
    week = request.form['week']
    team = request.form['team']

    week_info = NHL_Info(week, team)
    week_no = str(week_info.week)
    df_my_player_data = week_info.df_my_player_data
    df_all_player_data = week_info.df_all_player_data
    team_key = str(week_info.team_key)
    df_past = week_info.df_past
    points = round(week_info.total_points, 2)

    return render_template('view.html',
                           tables=[df_my_player_data.to_html(classes='table table-bordered table-striped table-hover player'),
                                   df_all_player_data.to_html(
                                       classes='table table-bordered table-striped table-hover player-all'),
                                   df_past.to_html(classes='table table-bordered table-striped table-hover player-all-past')],
                           titles=['na', '' + team + '\'s Team - Week ' + str(week_no), 'NHL YTD - League Stats & Week ' + str(week_no) + ' Projections', 'NHL Previous 3 Seasons - League Stats'], week_no=week_no, team=team, points=points)


if __name__ == "__main__":
    app.secret_key = 'A0Zr98j/3yX R~XHH!jmN]LWX/,?RT'
    app.run(host='localhost', port=5000, debug=True)
