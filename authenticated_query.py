from .utils import safe_post_request, depaginated_request
from .oauth_utils import get_oauth_token
import json
import argparse
import re

REQUIRED_CONFIG_KEYS = [
    "client_id",
    "client_secret"
]

REQUIRED_PAGINATE_VARIABLES = [
    "$page: Int",
    "$perPage: Int",
    "page: $page",
    "perPage: $perPage"
]

# python authenticated_query.py -q query.txt -o config.json -f results.json
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-q', '--query', help='text file containing a valid anilist GraphQL query', required=True)
    parser.add_argument('-o', '--oauth_config', help='config file containing client_id, client_secret', required=True)
    parser.add_argument('-f', '--file', help='optional parameter to output the results of the query')
    parser.add_argument(
        '-p', '--paginated', help='indicates if the query is paginated and should use depaginated_request', action='store_true')
    args = parser.parse_args()

    with open(args.oauth_config) as f:
        oauth_config = json.loads(f.read())
    if missing_keys := [key for key in REQUIRED_CONFIG_KEYS if key not in oauth_config]:
        raise Exception(f'Config is missing required keys: {missing_keys}')
    oauth_token = get_oauth_token(oauth_config['client_id'], oauth_config['client_secret'])

    with open(args.query) as f:
        query = f.read()

    if args.paginated:
        if any([re.match(paginate_var, query) is None for paginate_var in REQUIRED_PAGINATE_VARIABLES]):
            raise Exception('Query does not contain page and perPage as variables')
        user_json = depaginated_request(query, None, oauth_token)
    else:
        user_json = safe_post_request({'query': query}, oauth_token)

    if args.file:
        with open(args.file, 'w', encoding='utf8') as f:
            f.write(json.dumps(user_json))
