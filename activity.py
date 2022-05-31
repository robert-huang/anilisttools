from utils import URL, MAX_PAGE_SIZE, safe_post_request, depaginated_request
from oauth_utils import get_oauth_token
import json
import argparse
from datetime import datetime
import re

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
query ($userId: Int!, $page: Int, $perPage: Int, $mediaType: ActivityType) {{
  Page (page: $page, perPage: $perPage) {{
    pageInfo {{
      hasNextPage
    }}
    activities (userId: $userId, type: $mediaType, sort: ID) {{
      ... on ListActivity {{
        media {{
          siteUrl
          title {{
            {0}
          }}
        }}
        id
        type
        status
        progress
        createdAt
      }}
    }}
  }}
}}'''

# python activity.py -amdecf activity.json -n robert054321 -t romaji english native -o config.json
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--userId', default=839887)
    parser.add_argument('-n', '--username')
    parser.add_argument('-f', '--file', required=True)
    parser.add_argument('-a', '--anime', action='store_true')
    parser.add_argument('-m', '--manga', action='store_true')
    parser.add_argument('-d', '--full_date', action='store_true')
    parser.add_argument('-e', '--expand', action='store_true')
    parser.add_argument('-t', '--title_type', nargs='*',
                        choices=['english', 'romaji', 'native'], default=['romaji'])
    parser.add_argument('-c', '--completed_only', action='store_true',
                        help='filters to completed entries only, ignored when the expand flag is used')
    parser.add_argument('-o', '--oauth_config',
                        help='if a config file is provided with client_id and client_secret, run authenticated queries instead')
    args = parser.parse_args()
    if not (args.anime or args.manga):
        parser.error('one or more of the following arguments is required: -m/--manga, -a/--anime')

    oauth_token = None
    if args.oauth_config:
        with open(args.oauth_config) as f:
            args.oauth_config = json.loads(f.read())
        oauth_token = get_oauth_token(args.oauth_config['client_id'], args.oauth_config['client_secret'])

    user_json = safe_post_request(
            {'query': user_query.format(
                 "$userId: Int!" if args.username is None else "$username: String",
                 "id: $userId" if args.username is None else "name: $username"),
             'variables': {'userId': args.userId} if args.username is None else {'username': args.username}},
            oauth_token)
    user_id = user_json['User']['id']
    mediaType = "MEDIA_LIST" if args.anime and args.manga else "MANGA_LIST" if args.manga else "ANIME_LIST"
    activity = depaginated_request(query=query.format("\n".join(args.title_type)),
                                   variables={'userId': user_id, 'mediaType': mediaType})
    f = open(args.file, "w", encoding='utf8')
    f.write(json.dumps(user_json))
    f.write('\n')
    activity_date_parsed = [(a | {"createdAt": datetime.fromtimestamp(a['createdAt']).strftime(
        "%Y-%m-%d %H:%M:%S")}) if args.full_date else a for a in activity]
    activity = []
    if args.expand:
        for a in activity_date_parsed:
            if a['status'] in {'watched episode', 'read chapter'} and (nums := re.search('([0-9]+) - ([0-9]+)', a['progress'])):
                start_num, end_num = nums.group(1, 2)
                for num in range(int(start_num), int(end_num) + 1):
                    activity.append(json.dumps(
                        a | {"progress": str(num)}, ensure_ascii=False))
            else:
                activity.append(json.dumps(a, ensure_ascii=False))
    else:
        activity = [json.dumps(a, ensure_ascii=False)
                    for a in ([c for c in activity_date_parsed if c['status'] == 'completed'] if args.completed_only else activity_date_parsed)]
    f.write("\n".join(activity))
    f.close()
