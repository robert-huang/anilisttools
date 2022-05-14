import requests
import time

URL = 'https://graphql.anilist.co'
MAX_PAGE_SIZE = 50  # The anilist API's max page size


def safe_post_request(post_json):
    """Send a post request to the AniList API, automatically waiting and retrying if the rate limit was encountered.
    Returns the 'data' field of the response. Note that this may be None if the request found nothing (404).
    """
    response = requests.post(URL, json=post_json)

    # Handle rate limit
    if response.status_code == 429:
        retry_after = int(response.headers['Retry-After']) + 1
        time.sleep(retry_after)
        response = requests.post(URL, json=post_json)

    # If the rate limit error happens twice in a row I'd be interested to see it so no looping retry
    response.raise_for_status()

    return response.json()['data']


# Note that the anilist API's lastPage field of PageInfo is currently broken and doesn't return reliable results
def depaginated_request(query, variables):
    """Given a paginated query string, request every page and return a list of all the requested objects.

    Query must return only a single Page or paginated object subfield, and will be automatically unwrapped.
    """
    paginated_variables = {
        **variables,
        'perPage': MAX_PAGE_SIZE
    }

    out_list = []

    page_num = 1  # Note that pages are 1-indexed
    while True:
        paginated_variables['page'] = page_num
        response_data = safe_post_request({'query': query, 'variables': paginated_variables})

        # Blindly unwrap the returned json until we see pageInfo. This unwraps both Page objects and cases where we're
        # querying a paginated subfield of some other object.
        # E.g. if querying Media.staff.edges, unwraps "Media" and "staff" to get {"pageInfo":... "edges"...}
        while 'pageInfo' not in response_data:
            assert response_data, "Could not find pageInfo in paginated request."
            assert len(response_data) == 1, "Cannot de-paginate query with multiple returned fields."

            response_data = response_data[next(iter(response_data))]  # Unwrap

        # Grab the non-PageInfo query result
        assert len(response_data) == 2, "Cannot de-paginate query with multiple returned fields."
        out_list.extend(next(v for k, v in response_data.items() if k != 'pageInfo'))

        if not response_data['pageInfo']['hasNextPage']:
            return out_list

        page_num += 1
