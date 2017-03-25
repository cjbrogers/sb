#!/usr/bin/python

# from flask import current_app
import requests
from bs4 import BeautifulSoup
import pandas as pd
import myql
from yahoo_oauth import OAuth1
from myql import MYQL
import xml.etree.ElementTree as ET
import sqlalchemy
from sqlalchemy import create_engine
import pymysql
import pymysql.cursors


class Update:

    # only consumer_key and consumer_secret are required.
    oauth = OAuth1(None, None, from_file='../oauth1.json')
    guid = oauth.guid
    consumer_key = oauth.consumer_key
    consumer_secret = oauth.consumer_secret
    session_handle = oauth.session_handle
    access_token_secret = oauth.access_token_secret
    yql = MYQL(format='xml', oauth=oauth)

    league_key = 'nhl.l.22070'
    my_team_key = '363.l.22070.t.9'

    NSMAP = {'yh': 'http://fantasysports.yahooapis.com/fantasy/v2/base.rng'}

    pd.set_option('precision', 2)
    # relative location of fantasy league relevant statistical categories in
    # player statistics array
    skater_stat_ids = [1, 2, 3, 4, 6, 12, 13, 14, 15, 17]

    no_NHL_teams = 30
    team_abbr = ['ANA', 'ARI', 'BOS', 'BUF', 'CGY', 'CAR', 'CHI', 'COL', 'COB', 'DAL', 'DET', 'EDM', 'FLA', 'LOS',
                 'MIN', 'MON', 'NAS', 'NJD', 'NYI', 'NYR', 'OTT', 'PHI', 'PIT', 'SAN', 'STL', 'TAM', 'TOR', 'VAN', 'WAS', 'WPG']

    # TODO: Make the week work dynamically, i.e. so that the tables update based on the current week of play
    # TODO: Also make a link the user can click to update the data
    def __init__(self, week=23, app=None):
        self.week = week
        self.week_corrected = None
        self.app = app
        if self.week == [x for x in range(0, 10)]:
            self.week_corrected = "0{}".format(str(self.week))
        else:
            self.week_corrected = self.week
        self.engine = create_engine(
            'mysql+pymysql://root:jamesonrogers@localhost:3306/db_fhlo', echo=False, poolclass=sqlalchemy.pool.NullPool)

    def update_league_info(self):
        if not self.oauth.token_is_valid():
            self.oauth.refresh_access_token()

        response = self.yql.raw_query(
            'select * from fantasysports.leagues.standings where league_key in ("' + self.league_key + '")')
        if response == None:
            response = self.yql.raw_query(
                'select * from fantasysports.leagues.standings where league_key in ("' + self.league_key + '")')

        league_tree = ET.fromstring(response.text)

        # get the league info
        league = []
        self.team_keys = {}
        for team in league_tree.findall('.//yh:team', namespaces=self.NSMAP):
            name = team.find('.//yh:name', namespaces=self.NSMAP).text
            rank = int(team.find('.//yh:rank', namespaces=self.NSMAP).text)
            wins = int(team.find('.//yh:wins', namespaces=self.NSMAP).text)
            losses = int(team.find('.//yh:losses', namespaces=self.NSMAP).text)
            ties = int(team.find('.//yh:ties', namespaces=self.NSMAP).text)
            wlt = '{}-{}-{}'.format(wins, losses, ties)

            points = \
                float(team.find('.//yh:points_for', namespaces=self.NSMAP).text)

            self.team_key = team.find(
                './/yh:team_key', namespaces=self.NSMAP).text
            self.team_keys[self.team_key] = self.team_key
            email = team.find('.//yh:email', namespaces=self.NSMAP).text
            draft_position = team.find(
                './/yh:draft_position', namespaces=self.NSMAP).text
            moves = team.find('.//yh:number_of_moves',
                              namespaces=self.NSMAP).text
            trades = team.find('.//yh:number_of_trades',
                               namespaces=self.NSMAP).text

            league.append(
                {'name': name, 'rank': rank, 'w-l-t': wlt, 'points': points, 'team_key': self.team_key, 'draft_pos': draft_position, 'moves': moves, 'trades': trades})

        df_league = pd.DataFrame(league, columns=['name', 'rank', 'w-l-t',
                                                  'points', 'moves', 'trades', 'draft_pos', 'team_key'])
        # df_league.set_index(['name'], inplace=True)

        df_league.to_sql(con=self.engine, name='df_league_{}'.format(
            self.week_corrected), if_exists='replace', index=False)

        return df_league

    def update_roster_info(self):
        # TODO: build this out
        return

    '''
    Scrapes Yahoo to find the games per week per NHL team
    @params [self]
    @returns [df_games_per_team]    a dataframe of games per week per team
    '''

    def get_games_per_team(self):

        # make connection to Yahoo games per week page
        page = requests.get(
            "https://hockey.fantasysports.yahoo.com/hockey/team_games?week=" + str(self.week) + "")

        soup = BeautifulSoup(page.content, 'html.parser')

        teams = []
        unparsed_teams = soup.select("td div a")
        # get the teams
        for i in range(len(unparsed_teams)):
            teams.append(unparsed_teams[i].get_text())

        no_games = []
        unparsed_games = soup.find_all("td", class_="stat Tst-games")
        # get the number of games
        for i in range(len(unparsed_games)):
            no_games.append(unparsed_games[i].get_text())

        assert len(teams) == len(no_games), \
            "Length of teams: %r is not equal to length of no_games: %r." % (
                len(teams), len(no_games))

        # put them in a dictionary
        team_games = dict(zip(teams, no_games))
        # parse the results to get rid of unwanted teams
        team_games = {k: v for k, v in team_games.items()
                      if "All-Stars" not in k}

        assert len(team_games) == self.no_NHL_teams, \
            "There are: %r teams in the NHL but team_games is of size: %r." % (
                self.no_NHL_teams, len(team_games))

        # replace the long team names with abbreviations
        self.set_NHL_teams(team_games.keys())
        team_games = {self.teams_dict[k]: v for k, v in team_games.items()}

        df_games_per_team = pd.DataFrame.from_dict(
            data=team_games, orient='index')
        df_games_per_team.columns = ['Games_This_Week']
        df_games_per_team.index.name = 'Team'

        df_games_per_team = df_games_per_team.convert_objects(
            convert_numeric=True)

        return df_games_per_team

    def get_fantasy_roster_info(self, team_key, df_all_player_data):

        if not self.oauth.token_is_valid():
            self.oauth.refresh_access_token()

        response = self.yql.raw_query(
            'select * from fantasysports.teams.roster where team_key in ("' + team_key + '")')
        roster_tree = ET.fromstring(response.text)
        players = {}
        for player in roster_tree.findall('.//yh:player', namespaces=self.NSMAP):
            name = player.find('.//yh:full', namespaces=self.NSMAP).text
            # img_url = name = player.find('.//yh:url', namespaces=self.NSMAP).text
            selected_position = player.find(
                './/yh:selected_position', namespaces=self.NSMAP)
            position = selected_position.find(
                './/yh:position', namespaces=self.NSMAP).text
            players[name] = position

        df_my_player_data = df_all_player_data.loc[players.keys()]
        df_my_player_data = df_my_player_data[[
            'Team', 'GP', 'Points', 'Average_PPG']]
        df_my_player_data['Roster_Position'] = players.values()

        return df_my_player_data

    '''
    Setter for NHL teams in the league, including mapping the full names to the respective abbreviations
    @params [self]
    @returns [team_games]    a dictionary of {team,no_games} key value pairs
    '''

    def set_NHL_teams(self, teams):
        self.teams = sorted(teams)
        self.teams_dict = dict(zip(self.teams, self.team_abbr))

    '''
    Queries database to get past 3 seasons of player data
    @params [self]
    @returns [df]    pandas dataframe of player stats with player name as the index
    '''

    def get_past_3_seasons_player_stats(self):
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                # Read a single record
                sql = "SELECT * FROM `seasons_past`"
                cursor.execute(sql)

                df = pd.DataFrame(cursor.fetchall(), columns=['fname', 'lname', 'age', 'pos', 'gp_1314', 'gp_1415', 'gp_1516',
                                                              'pts_1314', 'pts_1415', 'pts_1516'])

                df["name"] = df["fname"] + ' ' + df["lname"]
                df.set_index(['name'], inplace=True)
                del df['fname']
                del df['lname']

                df["avg_gp"] = \
                    df[['gp_1314', 'gp_1415', 'gp_1516']].mean(axis=1)

                df["avg_pts"] = \
                    df[['pts_1314', 'pts_1415', 'pts_1516']].mean(axis=1)

                df["avg_ppg"] = df["avg_pts"] / df["avg_gp"]

                # rename the columns for aesthetics
                df = df.rename(columns={'name': 'Name', 'pos': 'Position', 'age': 'Age', 'gp_1314': 'GP_1314', 'gp_1415': 'GP_1415',
                                        'gp_1516': 'GP_1516', 'avg_gp': 'Average_GP_Past',
                                        'pts_1314': 'Points_1314', 'pts_1415': 'Points_1415',
                                        'pts_1516': 'Points_1516', 'avg_pts': 'Average_Points_Past',
                                        'avg_ppg': 'Average_PPG_Past'})
            return df
        finally:
            connection.close()

    '''
    Scrapes Yahoo to find the YTD NHL player statistics and prints a table of the results
    @params [self]
    '''

    def ytd_player_details(self):

        page = requests.get(
            "https://ca.sports.yahoo.com/nhl/stats/byposition?pos=C,RW,LW,D")
        soup = BeautifulSoup(page.content, 'html.parser')

        unparsed_headers = soup.find_all("a", class_="ysptblhdrsts")
        headers = []
        # get the headers
        for i in range(len(unparsed_headers)):
            headers.append(unparsed_headers[i].get_text())
        headers = [headers[i]
                   for i in range(len(headers)) if i in self.skater_stat_ids]
        headers.remove('PPG')
        headers.remove('SHG')
        headers = [s.replace('PPA', 'PPP') for s in headers]
        headers = [s.replace('SHA', 'SHP') for s in headers]
        headers.append('Points')
        headers.append('Average_PPG')

        # get the player data
        unparsed_data = soup.find_all("td", class_="yspscores")
        data = []
        for i in range(len(unparsed_data)):
            data.append(unparsed_data[i].get_text())
        # clear unwanted spaces
        data = [s.strip() for s in data]
        data = list(filter(None, data))
        # split each player into their own list, all of which are appended to a
        # new list
        player_data = [data[x:x + 19] for x in range(0, len(data), 19)]
        player_names = [data[i][:] for i in range(0, len(data), 19)]
        relevant_player_data = []
        points = None
        average_ppg = None
        for player in player_data:
            for i in range(len(player)):
                name = player[0]
                team = player[1]
                gp = player[2]
                g = player[3]
                a = player[4]
                pim = player[6]
                ppp = int(player[12]) + int(player[13])
                shp = int(player[14]) + int(player[15])
                sog = player[17]
                if i in self.skater_stat_ids:
                    if i == 12:
                        relevant_player_data.append(ppp)
                    elif i == 14:
                        relevant_player_data.append(shp)
                    elif i == 13 or i == 15:
                        pass
                    else:
                        relevant_player_data.append(player[i])
                points = (int(g) * (3) + int(a) * (2) + int(pim) * (0.25) +
                          int(ppp) * (0.5) + int(shp) * (1) + int(sog) * (0.5))
                average_ppg = points / int(gp)
            relevant_player_data.append(points)
            relevant_player_data.append(average_ppg)

        final_relevant_player_data = \
            [relevant_player_data[x:x + 10]
                for x in range(0, len(relevant_player_data), 10)]

        df_player_data = pd.DataFrame(
            data=final_relevant_player_data, columns=headers, index=player_names)

        # TODO: get all player data here
        # df_player_data_all.to_sql(con=self.engine, name='player_data_all', if_exists='replace', index=False)
        df_player_data.index.name = 'Name'
        return df_player_data

    def get_projected_points(self, team_key=None):
        print "get_projected_points(self, team_key=None)"
        if team_key == None:
            team_key = self.team_key
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT SUM(Projected_Points) as sum_points FROM `df_my_player_data_{}_{}` WHERE Roster_Position != 'BN' AND Roster_Position != 'IR'".format(
                    team_key, self.week_corrected)
                cursor.execute(sql)
                sum_points = cursor.fetchall()
                points = sum_points[0]['sum_points']
                print points
        except Exception as e:
            raise
        else:
            print "  success getting summed points from db"
            return points
        finally:
            connection.close()

    '''
    Establishes a connection to the mySQL db
    @params [self]
    @return [connection]
    '''

    def connect(self):
        # Connect to the database
        try:
            print "Attempting connection to database..."
            connection = pymysql.connect(host='localhost',
                                         port=3306,
                                         user='root',
                                         password='jamesonrogers',
                                         db='db_fhlo',
                                         cursorclass=pymysql.cursors.DictCursor)
        except Exception as e:
            raise
        else:
            print "Database successfully connected."
            return connection

    def main(self):
        try:
            df = pd.read_sql_table('df_league_{}'.format(
                self.week_corrected), con=self.engine)
        except:
            print "no tables for given week"
            self.app.df_league = self.update_league_info()

            print "UPDATING ALL WEEK INFO"
            df_all_player_data = self.ytd_player_details()
            df_games_per_team = self.get_games_per_team()

            df_past = self.get_past_3_seasons_player_stats()
            self.df_past_relevant = df_past[[
                'Age', 'Position', 'Average_PPG_Past']]

            df_all_player_data = pd.merge(df_all_player_data, df_games_per_team,
                                          right_on=df_games_per_team.index.values, left_on=df_all_player_data.Team, right_index=True)
            projected_points = df_all_player_data.Average_PPG * \
                df_all_player_data.Games_This_Week
            df_all_player_data['Projected_Points'] = projected_points

            for k, v in self.team_keys.iteritems():
                print 'TEAM KEY', v
                df_my_player_data = self.get_fantasy_roster_info(
                    v, df_all_player_data)
                df_my_player_data = pd.merge(df_my_player_data, df_games_per_team,
                                             right_on=df_games_per_team.index.values, left_on=df_my_player_data.Team, right_index=True)

                df_my_player_data = df_my_player_data.join(
                    self.df_past_relevant)
                projected_points = df_my_player_data.Average_PPG * \
                    df_my_player_data.Games_This_Week
                df_my_player_data['Projected_Points'] = projected_points

                # df_my_player_data = df_my_player_data.reset_index(inplace=False)
                df_my_player_data['Name'] = df_my_player_data.index

                df_my_player_data = df_my_player_data[['Name', 'Team', 'Position', 'Roster_Position', 'Age',
                                                       'GP', 'Points', 'Average_PPG', 'Games_This_Week', 'Average_PPG_Past', 'Projected_Points']]

                # create or replace sql tables with updated information
                df_my_player_data.to_sql(con=self.engine, name="df_my_player_data_{}_{}".format(
                    v, self.week_corrected), if_exists='replace', index=False)

                print 'TEAM KEY', v

            df_all_player_data.reset_index(inplace=True)
            # df_past.reset_index(inplace=True)
            df_past['Name'] = df_past.index

            df_past = df_past[['Name', 'Position', 'Age', 'GP_1314', 'GP_1415',
                               'GP_1516', 'Average_GP_Past', 'Points_1314', 'Points_1415', 'Points_1516', 'Average_Points_Past', 'Average_PPG_Past']]
            df_past.to_sql(con=self.engine, name="df_past",
                           if_exists='replace', index=False)
            df_all_player_data.to_sql(
                con=self.engine, name="df_all_player_data", if_exists='replace', index=False)

            self.app.df_league = self.app.df_league.rename(columns={'name': 'Name', 'rank': 'Rank', 'w-l-t': 'Wins-Losses-Ties', 'points': 'Points', 'trades': 'Trades', 'moves': 'Moves', 'draft_pos': 'Draft Position', 'team_key': 'Key'})
            proj_points = {}
            try:
                for key in self.app.df_league['Key']:
                    print "  Key to get projected points for:", key
                    proj_points[key] = [self.get_projected_points(key)]
                df_points = pd.DataFrame.from_dict(proj_points, orient='index')
                df_points = df_points.rename(columns={0: 'Projected_Points'})
                print df_points

                self.app.df_league = self.app.df_league.merge(
                    df_points, left_on=self.app.df_league.Key, right_on=df_points.index.values)
                print self.app.df_league
            except Exception as e:
                print e
            else:
                print "  success appending Projected_Points to league dataframe"

            return self.app.df_league
        else:
            print "ALREADY UPDATED THIS WEEK"
            df = df.rename(columns={'name': 'Name', 'rank': 'Rank', 'w-l-t': 'Wins-Losses-Ties', 'points': 'Points', 'trades': 'Trades',
                                                    'moves': 'Moves', 'draft_pos': 'Draft Position', 'team_key': 'Key'})
            proj_points = {}
            try:
                for key in df['Key']:
                    print "  Key to get projected points for:", key
                    proj_points[key] = [self.get_projected_points(key)]
                df_points = pd.DataFrame.from_dict(proj_points, orient='index')
                df_points = df_points.rename(columns={0: 'Projected_Points'})
                print df_points

                df = df.merge(df_points, left_on=df.Key,
                              right_on=df_points.index.values)
                print df
            except Exception as e:
                print e
            else:
                print "  success appending Projected_Points to league dataframe"
            return df
