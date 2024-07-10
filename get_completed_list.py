from request_utils import safe_post_request, depaginated_request
import oauth
# from oauth_utils import get_oauth_token
import json
import argparse
from datetime import datetime
import re

REQUIRED_CONFIG_KEYS = [
    'client_id',
    'client_secret'
]

user_query = '''
query ($username: String) {
    User (name: $username) {
    id
    name
    mediaListOptions {
      scoreFormat
      rowOrder
    }
    statistics {
        anime {
        count
        meanScore
        standardDeviation
        minutesWatched
        episodesWatched
      }
        manga {
        count
        meanScore
        standardDeviation
        chaptersRead
        volumesRead
      }
    }
  }
}
'''

list_query = '''
query ($userId: Int!, $mediaType: MediaType) {
  MediaListCollection(userId: $userId, type: $mediaType, sort:[SCORE_DESC, ADDED_TIME_DESC], forceSingleCompletedList: true, status: COMPLETED) {
  	lists {
  	  name
  	  status
      entries {
        media {
          id
          title {
            romaji
          }
          format
        }
        score (format: POINT_100)
        startedAt {
          year
          month
          day
        }
        completedAt {
          year
          month
          day
        }
        notes
      }
  	}
  }
}'''

# python activity.py -amef activity.json -n robert054321 -t [romaji/english/native] -o config.json -d
# python activity.py -amef activity_expanded.json
# python activity.py -amcf activity_completed.json
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('username', help="User whose list should be checked.")
    parser.add_argument('-f', '--file')
    args = parser.parse_args()

    oauth_token = oauth.get_oauth_token(args.username)

    output = []

    user_json = safe_post_request({'query': user_query, 'variables': {'username': args.username}}, oauth_token=oauth_token)
    output.append(json.dumps(user_json))

    user_id = user_json['User']['id']
    username = user_json['User']['name']

    scores = {}

    anime_scores_json = safe_post_request(
        {'query': list_query, 'variables': {'userId': user_id, 'mediaType': 'ANIME'}}, oauth_token=oauth_token)
    output.append(json.dumps(anime_scores_json))
    if anime_scores_json['MediaListCollection']['lists'][0]['name'] != 'Completed':
        raise Exception('not completed list fix your script idiot')
    for entry in anime_scores_json['MediaListCollection']['lists'][0]['entries']:
        # print(entry)
        score = None if entry['score'] == 0 else entry['score']
        scores.setdefault(str(score), []).append(entry)
    manga_scores_json = safe_post_request(
        {'query': list_query, 'variables': {'userId': user_id, 'mediaType': 'MANGA'}}, oauth_token=oauth_token)
    output.append(json.dumps(manga_scores_json))
    for entry in manga_scores_json['MediaListCollection']['lists'][0]['entries']:
        score = None if entry['score'] == 0 else entry['score']
        scores.setdefault(str(score), []).append(entry)

    json_filename = args.file if args.file else f"scores_json_{username}.json"
    with open(json_filename, 'w', encoding='utf8') as f:
        f.write('\n\n'.join(output))

    with open(f"scores_{username}.csv", 'w', encoding='utf8') as f:
        f.write('title, score\n')
        for score, entries in sorted(scores.items(), key=lambda x: 0 if x[0] == 'None' or x[0] is None else int(x[0]), reverse=True):
            for entry in entries:
                f.write(f"{entry['media']['title']['romaji']} ({entry['media']['format']}), {score}\n")
