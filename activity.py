from utils import URL, MAX_PAGE_SIZE, safe_post_request, depaginated_request
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
query ($userId: Int!, $page: Int, $perPage: Int, $mediaType: ActivityType) {
  Page (page: $page, perPage: $perPage) {
    pageInfo {
      hasNextPage
    }
    activities (userId: $userId, type: $mediaType, sort: ID) {
      ... on ListActivity {
        media {
          siteUrl
          title {
            romaji
          }
        }
        id
        type
        status
        progress
        createdAt
      }
    }
  }
}'''

# python activity.py -amdf activity.json -un robert054321 -e
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--userId', dest='userId', default=839887)
    parser.add_argument('-un', '--username', dest='username')
    parser.add_argument('-f', '--file', dest='file', required=True)
    parser.add_argument('-a', '--anime', dest='anime', action='store_true')
    parser.add_argument('-m', '--manga', dest='manga', action='store_true')
    parser.add_argument('-d', '--date', dest='full_date', action='store_true')
    parser.add_argument('-e', '--expand', dest='expand', action='store_true')
    args = parser.parse_args()
    if not (args.anime or args.manga):
        parser.error(
            'one or more of the following arguments are required: -m/--manga, -a/--anime')

    user_json = safe_post_request(
           {'query': user_query.format(
                 "$userId: Int!" if args.username is None else "$username: String",
                 "id: $userId" if args.username is None else "name: $username"),
            'variables': {'userId': args.userId} if args.username is None else {'username': args.username}})
    user_id = user_json['User']['id']
    mediaType = "MEDIA_LIST" if args.anime and args.manga else "MANGA_LIST" if args.manga else "ANIME_LIST"
    activity = depaginated_request(query=query,
                                   variables={'userId': user_id, 'mediaType': mediaType})
    f = open(args.file, "w")
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
                    activity.append(json.dumps(a | {"progress": str(num)}))
            else:
                activity.append(json.dumps(a))
    else:
        activity = [json.dumps(a) for a in activity_date_parsed]
    f.write("\n".join(activity))
    f.close()
