import requests
import pandas as pd
import myql
from yahoo_oauth import OAuth1
from myql import MYQL
import xml.etree.ElementTree as ET
import sqlalchemy
from sqlalchemy import create_engine
import pymysql
import pymysql.cursors
from update import Update


class NHL_Info:

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
    team_abbr = ['ANA', 'ARI', 'BOS', 'BUF', 'CGY', 'CAR', 'CHI', 'COL', 'COB', 'DAL', 'DET', 'EDM', 'FLA', 'LOS','MIN', 'MON', 'NAS', 'NJD', 'NYI',
    'NYR', 'OTT', 'PHI', 'PIT', 'SAN', 'STL', 'TAM', 'TOR', 'VAN', 'WAS', 'WPG']

    def __init__(self, week, team=None):
        self.week = week
        self.team = team
        self.week_corrected = ""
        if self.week == [x for x in range(0, 10)]:
            self.week_corrected = "0{}".format(str(self.week))
        else:
            self.week_corrected = str(self.week)
        self.engine = create_engine(
            'mysql+pymysql://root:jamesonrogers@localhost:3306/db_fhlo', echo=False, poolclass=sqlalchemy.pool.NullPool)
        self.df_league = self.get_fantasy_league_info()
        if team != None:
            self.team_key = str(
                self.df_league[self.df_league['Name'] == self.team].values[0][7])
            self.df_my_player_data = self.get_my_player_data()
            self.df_all_player_data = self.get_all_player_data()
            self.df_past = self.get_past()
            self.total_points = self.get_projected_points(self.team_key)

    def get_my_player_data(self):
        # connection = self.connect()
        try:
            with self.engine.connect() as conn:
                sql = "SELECT * FROM `df_my_player_data_{}_{}`".format(
                    self.team_key, self.week_corrected)
                # cursor.execute(sql)
                columns = ['Name', 'Age', 'Team', 'Position', 'GP', 'Points',
                           'Average_PPG_Past', 'Average_PPG', 'Games_This_Week', 'Projected_Points']
                df_my_player_data = pd.read_sql(sql=sql, con=conn)
        except Exception as e:
            raise
        else:
            print "success getting df_my_player_data from db"
        return df_my_player_data

    def get_all_player_data(self):
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM `df_all_player_data`"
                cursor.execute(sql)
                columns = ['Name', 'Team', 'GP', 'G', 'A', 'PIM', 'PPP', 'SHP',
                           'Points', 'Average_PPG', 'Games_This_Week', 'Projected_Points']
                df_all_player_data = pd.DataFrame(
                    cursor.fetchall(), columns=columns)
        finally:
            connection.close()
        return df_all_player_data

    def get_past(self):
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM `df_past`"
                cursor.execute(sql)
                columns = ['name', 'Age', 'Position', 'GP_1314', 'GP_1415', 'GP_1516', 'AverageAverage_GP_Past',
                           'Points_1314', 'Points_1415', 'Points_1516', 'AverAverage_Points_Past', 'Average_PPG_Past']
                df_past = pd.DataFrame(cursor.fetchall())
                df_past.rename(columns={'name': 'Name'}, inplace=True)
                df_past = df_past[['Name', 'Position', 'Age', 'GP_1314',
                                    'GP_1415', 'GP_1516', 'Average_GP_Past', 'Points_1314', 'Points_1415', 'Points_1516', 'Average_Points_Past', 'Average_PPG_Past']]
        finally:
            connection.close()
        return df_past

    def get_fantasy_league_info(self):
        print "*get_fantasy_league_info(self)"
        connection = self.connect()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM `df_league_{}`".format(
                    self.week_corrected)
                cursor.execute(sql)

                df = pd.DataFrame(cursor.fetchall(), columns=[
                                  'name', 'rank', 'w-l-t', 'points', 'trades', 'moves', 'draft_pos', 'team_key'])

                # rename the columns for aesthetics
                df = df.rename(columns={'name': 'Name', 'rank': 'Rank', 'w-l-t': 'Wins-Losses-Ties', 'points': 'Points', 'trades': 'Trades',
                                        'moves': 'Moves', 'draft_pos': 'Draft Position', 'team_key': 'Key'})
                proj_points = {}
                try:
                    for key in df['Key']:
                        print "  Key to get projected points for:", key
                        proj_points[key] = [self.get_projected_points(key)]
                    df_points = pd.DataFrame.from_dict(
                        proj_points, orient='index')
                    df_points = df_points.rename(
                        columns={0: 'Projected_Points'})
                    print df_points

                    df = df.merge(df_points, left_on=df.Key,
                                  right_on=df_points.index.values)
                    print df
                except Exception as e:
                    print e
                else:
                    print "  success appending Projected_Points to league dataframe"
                    # return df

        except:
            print "  don't have current week info so get it"
            update = Update(self.week, self)
            return update.main()
        else:
            print "  successfully got current week fantasy league info from the database"
            return df
        finally:
            connection.close()

    '''
    Queries database to get past 3 seasons of player data
    @params [self]
    @returns [df]    pandas dataframe of player stats with player name as the index
    '''

    def get_past_3_seasons_player_stats(self):
        print "get_past_3_seasons_player_stats(self)"
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
        finally:
            connection.close()
            return df

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
        print "connect(self)"
        # Connect to the database
        try:
            print "  Attempting connection to database..."
            connection = pymysql.connect(host='localhost',
                                         port=3306,
                                         user='root',
                                         password='jamesonrogers',
                                         db='db_fhlo',
                                         cursorclass=pymysql.cursors.DictCursor)
        except Exception as e:
            raise
        else:
            print "  Database successfully connected."
            return connection
