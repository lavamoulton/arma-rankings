import datetime
import json
import operator
from trueskill import Rating, TrueSkill
from os import sys, path, listdir

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

from app import db
from app.models import User, Trueskillrating, Match, MatchScore

base_addition = 1500
multiplier = 23.45


def transform_rating(mu, sigma):
    return round((mu - 3 * sigma) * multiplier + base_addition, 0)


def match_already_exists(match_name, match_type):
    matching_match_count = db.session.query(Match).filter(Match.name.like(match_name), Match.matchtype.like(match_type)).count()
    if matching_match_count > 0:
        return True
    else:
        return False


def user_already_exists(username):
    matching_user_count = db.session.query(User).filter(User.username.like(username)).count()
    if matching_user_count > 0:
        return True
    else:
        return False


match_type = ''
directory_to_scan = '/home/ranking_app/raw_data'

for filename in listdir(directory_to_scan):
    with open(directory_to_scan + '/' + filename) as f:
        if '.txt' in filename:
            # do nothing
            print('This is a .txt file. Carrying on.')
            continue
        print('Ranking: ' + filename)
        matches_json = json.load(f)
        matches = matches_json['match_results']
        username_to_rating = {}

        pickup_fort_type = 0
        pickup_tst_type = 0

        starting_mu = 25.0
        starting_sigma = 8.333333333333334
        starting_beta = 4.166666666666667
        starting_tau = 4.166666666666667
        if 'pickup-fortress' in filename: 
            pickup_fort_type = 1
            starting_rating = transform_rating(starting_mu, starting_sigma)
            print('Initializing trueskill rating with starting_rating %d' % starting_rating)
            env = TrueSkill(mu=starting_mu, sigma=starting_sigma, draw_probability=0.0, beta=starting_beta, tau=starting_tau)
        if 'pickup-tst' in filename:
            pickup_tst_type = 1
            # using the default mu and sigma here
            starting_rating = transform_rating(mu=starting_mu, sigma=starting_sigma)
            env = TrueSkill()
        else: 
            # using the default mu and sigma here
            starting_rating = transform_rating(mu=starting_mu, sigma=starting_sigma)
            env = TrueSkill()
        env.make_as_global()

        if pickup_fort_type or pickup_tst_type:
            for match in matches:
                # if this match already exists in the DB, we don't want to do anything with it, so we'll carry on to the next match
                if match_already_exists(match['name'], match['matchtype']):
                    print("Found a duplicate match with name: " + match['name'])
                    continue
                match_type = match['matchtype']
                match_date_obj = datetime.datetime.strptime(match['date'], "%Y-%m-%d")
                match_data = Match(
                    name=match['name'],
                    matchtype=match_type,
                    date=match_date_obj
                )
                db.session.add(match_data)
                db.session.flush()  # This will give us an ID for the match that has not yet been commited
                formatted_match = {'team_rankings': [], 'team_weights': {}}
                match_teams_list = match['teams']
                sorted_teams = sorted(match_teams_list, key=lambda x: x['score'], reverse=True)
                place = 1
                total_rounds = match['stats']['total_rounds']
                match_scores = {}
                for sorted_team in sorted_teams:
                    team_rankings = {}
                    player_count = 0
                    for unsorted_team in match_teams_list:
                        if sorted_team['team_name'] == unsorted_team['team_name']:
                            for player in sorted(unsorted_team['players'], key=lambda x: x['score'], reverse=True):
                                username = player['username']
                                username = username.replace("\_"," ")
                                rating_weight = 1
                                if username_to_rating.has_key(username):
                                    rating = username_to_rating[username]['rating']
                                else:
                                    rating = Rating(mu=starting_mu)
                                if player['rounds_played'] < total_rounds:
                                    print('A player did not play the full match: %s' % player['username'])
                                    print('Rounds played: %d | Total rounds: %d' % (player['rounds_played'], total_rounds), float(player['rounds_played'])/float(total_rounds))
                                    rating_weight = float(player['rounds_played'])/float(total_rounds)
                                team_rankings[username] = {
                                    'rating': rating,
                                    'weight': rating_weight
                                }
                                transformed_rating = transform_rating(rating.mu, rating.sigma)
                                match_score = MatchScore(
                                    match_id=match_data.id,
                                    username=username,
                                    score=player['score'],
                                    place=place,
                                    rounds_played=player['rounds_played'],
                                    entry_rating=transformed_rating,
                                )
                                db.session.add(match_score)
                                match_scores[username] = match_score
                            match_rankings = {}
                            for team_ranking in team_rankings:
                                player_count = player_count + 1
                                match_rankings[team_ranking] = team_rankings[team_ranking]['rating']
                                formatted_match['team_weights'][(player_count, team_ranking)] = team_rankings[team_ranking]['weight']
                            formatted_match['team_rankings'].append(match_rankings)
                            print('\n\nRANKINGS - Team name: %s, num players: %d \n\n' % (unsorted_team['team_name'], len(match_rankings)))
                            print('WEIGHT - Team name: %s, num players: %d \n\n' % (unsorted_team['team_name'], len(formatted_match['team_weights'])))
                            place += 1
                try:
                    print('TEAM RANKINGS COMBINED : %s \n\n' % str(formatted_match['team_rankings']))
                    print('TEAM WEIGHTS COMBINED : %s \n\n' % str(formatted_match['team_weights']))
                    # print(env.quality(formatted_match['team_rankings'], weights=formatted_match['team_weights']))
                    print(env.quality(formatted_match['team_rankings'], weights=formatted_match['team_weights']))
                    match_data.quality = round(100*env.quality(formatted_match['team_rankings'], weights=formatted_match['team_weights']), 2)
                except ValueError:
                    print("Cannot calculate this match")
                teams_ratings = env.rate(formatted_match['team_rankings'], weights=formatted_match['team_weights'])
                print('Team Ratings: ', teams_ratings, '\n\n')
                for team_ratings in teams_ratings:
                    for username, rating in team_ratings.items():
                        old_rating = starting_rating
                        if username in username_to_rating:
                            old_rating = transform_rating(username_to_rating[username]['rating'].mu, username_to_rating[username]['rating'].sigma)
                        new_rating = transform_rating(rating.mu, rating.sigma)
                        match_scores[username].exit_rating = new_rating
                        rating_data = {
                            'latest_delta': new_rating - old_rating,
                            'latest_delta_date': match_date_obj,
                            'rating': rating
                        }
                        username_to_rating[username] = rating_data
        else: 
            for match in matches:
                # if this match already exists in the DB, we don't want to do anything with it, so we'll carry on to the next match
                if match_already_exists(match['name'], match['matchtype']):
                    print("Found a duplicate match with name: " + match['name'])
                    continue
                if len(match['match_scores']) > 1:
                    match_type = match['matchtype']
                    match_date_obj = datetime.datetime.strptime(match['date'], "%Y-%m-%d")
                    match_data = Match(
                        name=match['name'],
                        matchtype=match_type,
                        date=match_date_obj
                    )
                    db.session.add(match_data)
                    db.session.flush() # This will give us an ID for the match that has not yet been commited
                    formatted_match = []
                    place = 1
                    match_scores = {}
                    for player in match['match_scores']:
                        username = player['username']
                        if (username_to_rating.has_key(username)):
                            rating = username_to_rating[username]['rating']
                            formatted_match.append({username: rating})
                        else:
                            rating = Rating()
                            formatted_match.append({username: rating})
                        transformed_rating = transform_rating(rating.mu, rating.sigma)
                        match_score = MatchScore(
                            match_id=match_data.id,
                            username=username,
                            score=player['score'],
                            place=place,
                            entry_rating=transformed_rating,
                        )
                        db.session.add(match_score)
                        match_scores[username] = match_score
                        place += 1 

                    match_data.quality = round(env.quality(formatted_match), 4)
                    ratings = env.rate(formatted_match)
                    for rating in ratings:
                        for username, rating in rating.items(): 
                            old_rating = starting_rating
                            if (username_to_rating.has_key(username)):
                                old_rating = transform_rating(username_to_rating[username]['rating'].mu, username_to_rating[username]['rating'].sigma)
                            new_rating = transform_rating(rating.mu, rating.sigma)
                            match_scores[username].exit_rating = new_rating
                            rating_data = {'latest_delta': new_rating - old_rating,
                                           'latest_delta_date': match_date_obj,
                                           'rating': rating}
                            username_to_rating[username] = rating_data
        for key in username_to_rating:
            if not (user_already_exists(key)):
                user = User(username=key)
                db.session.add(user)
            rating = transform_rating(username_to_rating[key]['rating'].mu, username_to_rating[key]['rating'].sigma)
            trueskillrating = Trueskillrating(
                username=key,
                matchtype=match_type,
                mu=round(username_to_rating[key]['rating'].mu, 2),
                sigma=round(username_to_rating[key]['rating'].sigma, 2),
                rating=rating,
                latest_delta=username_to_rating[key]['latest_delta'],
                latest_delta_date=username_to_rating[key]['latest_delta_date']
            )
            db.session.add(trueskillrating)
db.session.commit()
