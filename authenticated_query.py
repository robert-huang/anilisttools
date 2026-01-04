from request_utils import safe_post_request, depaginated_request
import oauth
# from oauth_utils import get_oauth_token
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

# python authenticated_query.py -q query.graphql -o config.json -f results.json -v variables.json
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-q', '--query', help='text file containing a valid anilist GraphQL query')
    parser.add_argument('-v', '--variables', help='text file containing variables used for the query', default='variables.json')
    # parser.add_argument('-o', '--oauth_config', help='config file containing client_id, client_secret')
    # parser.add_argument('-t', '--token', help='oauth token')
    parser.add_argument('-f', '--file', help='optional parameter to output the results of the query')
    parser.add_argument(
        '-p', '--paginated', help='indicates if the query is paginated and should use depaginated_request', action='store_true')
    parser.add_argument('-u', '--user', required=True)
    args = parser.parse_args()

    # oauth_token = None
    # if args.token:
    #     oauth_token = args.token
    # elif args.oauth_config:
    #     with open(args.oauth_config) as f:
    #         oauth_config = json.loads(f.read())
    #     saved_access_token = oauth_config.get('access_token')
    #     if saved_access_token:
    #         oauth_token = saved_access_token
    #     else:
    #         if missing_keys := [key for key in REQUIRED_CONFIG_KEYS if key not in oauth_config]:
    #             raise Exception(f'Config is missing required keys: {missing_keys}')
    #         oauth_token = get_oauth_token(oauth_config)
    #         with open('oauth_token.txt', 'w') as f:
    #             f.write(str(datetime.now()))
    #             f.write('\n')
    #             f.write(str(oauth_token))

    oauth_token = oauth.get_oauth_token(args.user)

    query_file = args.query
    with open(query_file) as f:
        query = f.read()

    variables_file = args.variables
    if variables_file:
        with open(variables_file) as f:
            variables = f.read()

    if args.paginated:
        if any([re.match(paginate_var, query) is None for paginate_var in REQUIRED_PAGINATE_VARIABLES]):
            raise Exception('Query does not contain page and perPage as variables')
        user_json = depaginated_request(query, variables, oauth_token=oauth_token)
    else:
        user_json = safe_post_request({'query': query, 'variables': variables}, oauth_token=oauth_token)

    filename = args.file if args.file else 'query_executed.json'
    with open(filename, 'w', encoding='utf8') as f:
        f.write(json.dumps(user_json))
