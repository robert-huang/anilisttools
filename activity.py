from request_utils import safe_post_request, depaginated_request
import oauth
# from oauth_utils import get_oauth_token
import json
import argparse
from datetime import datetime, date
import re

REQUIRED_CONFIG_KEYS = [
    'client_id',
    'client_secret'
]

user_query = '''
query ({0}) {{
    User ({1}) {{
    id
    name
    mediaListOptions {{
      scoreFormat
      rowOrder
    }}
    statistics {{
        anime {{
        count
        meanScore
        standardDeviation
        minutesWatched
        episodesWatched
      }}
        manga {{
        count
        meanScore
        standardDeviation
        chaptersRead
        volumesRead
      }}
    }}
  }}
}}
'''

query = '''
query ($userId: Int!, $page: Int, $perPage: Int, $mediaTypes: [ActivityType]) {{
  Page (page: $page, perPage: $perPage) {{
    pageInfo {{
      hasNextPage
    }}
    activities (userId: $userId, type_in: $mediaTypes, sort: ID) {{
      ... on ListActivity {{
        media {{
          siteUrl
          title {{
            {0}
          }}
          format
          chapters
          episodes
        }}
        id
        type
        status
        progress
        createdAt
        siteUrl
      }}
    }}
  }}
}}'''

list_query = '''
query ($userId: Int!, $mediaType: MediaType) {
  MediaListCollection(userId: $userId, type: $mediaType, sort:[SCORE_DESC, FINISHED_ON_DESC]) {
  	lists {
  	  name
  	  status
      entries {
        media {
            id
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
      }
  	}
  }
}'''

# python activity.py -amef activity.json -n robert054321 -t [romaji/english/native] -o config.json -d
# python activity.py -amef activity_expanded.json
# python activity.py -amcf activity_completed.json
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--userId', default=839887)
    parser.add_argument('-n', '--username', default='robert')
    parser.add_argument('-f', '--file')
    parser.add_argument('-a', '--anime', action='append_const', dest='media_types', const='ANIME_LIST')
    parser.add_argument('-m', '--manga', action='append_const', dest='media_types', const='MANGA_LIST')
    parser.add_argument('-e', '--expand', action='store_true')
    parser.add_argument('-t', '--title_type', nargs='*',
                        choices=['english', 'romaji', 'native'], default=['romaji'])
    parser.add_argument('-c', '--completed_only', action='store_true',
                        help='filters to completed entries only, ignored when the expand flag is used')
    parser.add_argument('-o', '--oauth_config',
                        help='if config file is provided, run authenticated queries instead')
    parser.add_argument('-d', '--integer_datetime', action='store_true',
                        help='prevents formatting the dates to ISO strings, useful for data analysis (?)')
    args = parser.parse_args()
    if args.media_types is None:
        parser.error('one or more of the following arguments is required: -m/--manga, -a/--anime')

    oauth_token = oauth.get_oauth_token(args.username)
    # oauth_token = None
    # if args.oauth_config:
    #     with open(args.oauth_config) as f:
    #         oauth_config = json.loads(f.read())
    #     if missing_keys := [key for key in REQUIRED_CONFIG_KEYS if key not in oauth_config]:
    #         raise Exception(f'Config is missing required keys: {missing_keys}')
    #     oauth_token = get_oauth_token(oauth_config['client_id'], oauth_config['client_secret'])

    output = []

    user_json = safe_post_request(
            {'query': user_query.format(
                 '$userId: Int!' if args.username is None else '$username: String',
                 'id: $userId' if args.username is None else 'name: $username'),
             'variables': {'userId': args.userId} if args.username is None else {'username': args.username}},
            oauth_token=oauth_token)
    output.append(json.dumps(user_json))

    user_id = user_json['User']['id']
    activity_list = depaginated_request(query=query.format('\n'.join(args.title_type)),
                                        variables={'userId': user_id, 'mediaTypes': args.media_types})
    if not args.integer_datetime:
        activity_list = [(activity | {'createdAt': datetime.fromtimestamp(activity['createdAt']).strftime('%Y-%m-%d %H:%M:%S')})
                         for activity in activity_list]

    # expand overrides completed_only
    if args.expand:
        for activity in activity_list:
            if (activity['status'] in {'watched episode', 'read chapter'}
                    and (nums := re.search('([0-9]+) - ([0-9]+)', activity['progress']))):
                start_num, end_num = nums.group(1, 2)
                for num in range(int(start_num), int(end_num) + 1):
                    output.append(json.dumps(activity | {'progress': str(num)}, ensure_ascii=False))
            else:
                output.append(json.dumps(activity, ensure_ascii=False))
    else:
        if args.completed_only:
            anime_scores_json = safe_post_request(
                {'query': list_query, 'variables': {'userId': user_id, 'mediaType': 'ANIME'}}, oauth_token=oauth_token)
            entries = [(str(entry['media']['id']), [None if entry['score'] == 0 else entry['score'], entry['startedAt'], entry['completedAt']])
                        for sublist in anime_scores_json['MediaListCollection']['lists']
                        for entry in sublist['entries']]
            manga_scores_json = safe_post_request(
                {'query': list_query, 'variables': {'userId': user_id, 'mediaType': 'MANGA'}}, oauth_token=oauth_token)
            entries.extend([(str(entry['media']['id']), [None if entry['score'] == 0 else entry['score'], entry['startedAt'], entry['completedAt']])
                            for sublist in manga_scores_json['MediaListCollection']['lists']
                            for entry in sublist['entries']])
            entries = dict(entries)
            for activity in [activity for activity in activity_list if activity['status'] == 'completed']:
                media_id = re.match('https://anilist.co/(manga|anime)/([0-9]*)', activity['media']['siteUrl'])[2]
                list_entry = entries.get(media_id, [None, None, None])
                if activity['media']['format'] in ["MANGA", "NOVEL", "ONE_SHOT"]:
                    length = ('chapters', activity['media']['chapters'])
                else:
                    length = ('episodes', activity['media']['episodes'])
                activity = {
                    'title': activity['media']['title'].get('romaji') if 'romaji' in activity['media']['title']
                             else next(iter(activity['media']['title'].values())),
                    'score': list_entry[0],
                    'type': activity['media']['format'],
                    length[0]: length[1],
                    'completedActivity': activity['createdAt']
                }
                if (list_entry[1] and list_entry[1]['year'] and list_entry[2] and list_entry[2]['year']):
                    startedAt = datetime(list_entry[1]['year'], list_entry[1]['month'], list_entry[1]['day'])
                    completedAt = datetime(list_entry[2]['year'], list_entry[2]['month'], list_entry[2]['day'])
                    activity['startedDate'] = startedAt.strftime('%Y.%m.%d')
                    activity['completedDate'] = completedAt.strftime('%Y.%m.%d')
                    activity['duration'] = str((completedAt - startedAt).days).zfill(3)
                else:
                    activity['duration'] = None
                output.append(json.dumps(activity, ensure_ascii=False))
        else:
            output.extend([json.dumps(activity, ensure_ascii=False) for activity in activity_list])

    filename = args.file if args.file else f"activity_{args.username}_expanded_{str(date.today())}.json" if args.expand else f"activity_{args.username}_{str(date.today())}.json"
    with open(filename, 'w', encoding='utf8') as f:
        f.write('\n'.join(output))
