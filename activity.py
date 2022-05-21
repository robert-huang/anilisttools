from utils import URL, MAX_PAGE_SIZE, safe_post_request, depaginated_request
import json
import argparse
from datetime import datetime

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

anime_query = '''
query ($userId: Int!, $page: Int, $perPage: Int) {
  Page (page: $page, perPage: $perPage) {
    pageInfo {
      hasNextPage
    }
    activities (userId: $userId, type_in: [ANIME_LIST], sort: ID) {
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

manga_query = '''
query ($userId: Int!, $page: Int, $perPage: Int) {
  Page (page: $page, perPage: $perPage) {
    pageInfo {
      hasNextPage
    }
    activities (userId: $userId, type_in: [MANGA_LIST], sort: ID) {
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

# python activity.py -f manga_activity.json -t m -un robert054321 -d
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--userId', dest='userId', default=839887)
    parser.add_argument('-un', '--username', dest='username')
    parser.add_argument('-f', '--file', dest='file', required=True)
    parser.add_argument('-t', '--type', dest='type', choices=['a', 'm', 'anime', 'manga'], required=True)
    parser.add_argument('-d', '--date', dest='full_date', action='store_true')
    args = parser.parse_args()

    user_json = safe_post_request(
	       {'query': user_query.format(
                 "$userId: Int!" if args.username is None else "$username: String",
                 "id: $userId" if args.username is None else "name: $username"),
            'variables': {'userId': args.userId} if args.username is None else {'username': args.username}})
    user_id = user_json['User']['id']
    activity = depaginated_request(
        query=anime_query if args.type in ['a', 'anime'] else manga_query,
        variables={'userId': user_id}
    )
    f = open(args.file, "w")
    f.write(json.dumps(user_json))
    f.write('\n')
    f.write("\n".join([json.dumps(a | {"createdAt": datetime.fromtimestamp(a['createdAt']).strftime("%Y-%m-%d %H:%M:%S")}) if args.full_date else json.dumps(a) for a in activity]))
    f.close()
