import argparse
import json
import random
import requests
import time

URL = 'https://graphql.anilist.co'
MAX_PAGE_SIZE = 50  # The anilist API's max page size


# Metrics to track and return top 5 of, in terms of shared completed shows:
# similarity score (normalizing for mean and standard deviation, where SD is measured with the max/min scores in mind
# cosine score
# max number of shows with a score exactly matching (rounded if they only use 1-10, .5 can go either up or down)
# TODO: Do something to factor in Drops


#pageInfo {
#     total
#     currentPage
#     lastPage
#     hasNextPage
#     perPage
# }


def safe_post_request(post_json):
    """Send a post request to the AniList API, automatically waiting and retrying if the rate limit was encountered.
    Returns the 'data' field of the response.
    """
    response = requests.post(URL, json=post_json)

    # Handle rate limit
    if response.status_code == 429:
        retry_after = int(response.headers['Retry-After']) + 1
        #print(f"Rate limit encountered; waiting {retry_after} seconds...\n")
        time.sleep(retry_after)
        response = requests.post(URL, json=post_json)

    # If the rate limit error happens twice in a row I'd be interested to see it so no looping retry
    response.raise_for_status()

    return response.json()['data']


def depaginated_request(query, variables):
    """Given a paginated query string, request every page and return a list of all the requested objects."""
    paginated_variables = {
        **variables,
        'perPage': MAX_PAGE_SIZE
    }

    out_list = []

    page_num = 1  # Note that pages are 1-indexed
    while True:
        paginated_variables['page'] = page_num
        response_data = safe_post_request({'query': query, 'variables': paginated_variables})
        # Grab the non-PageInfo query result (there must be exactly one in a Page query)
        out_list.extend(next(v for k, v in response_data['Page'].items() if k != 'pageInfo'))

        if not response_data['Page']['pageInfo']['hasNextPage']:
            return out_list

        page_num += 1


def get_user_id_from_name(username):
    """Given an AniList username, fetch the user's ID."""
    query_user_id = '''
query ($id: Int, $username: String) {
    User (id: $id, name: $username) {
        id
    }
}'''

    return safe_post_request({'query': query_user_id, 'variables': {'username': username}})['User']['id']


def get_user_completed_scores(user_id):
    """Given an AniList user ID, fetch the user's completed anime list, returning a dict of show_ID: score."""
    query_completed_list = '''
query ($userId: Int, $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            hasNextPage
        }
        # Note that a MediaList object is actually a single list entry, hence the need for pagination
        mediaList(userId: $userId, type: ANIME, status: COMPLETED, sort: SCORE_DESC) {
            mediaId
            # media {
            #     title {
            #         english
            #     }
            # }
            score
        }
    }
}'''

    return {list_entry['mediaId']: list_entry['score']
            for list_entry in depaginated_request(query=query_completed_list, variables={'userId': user_id})}


def get_followed_users(user_id):
    """Return a list of users followed by the given user ID."""
    query_followed = '''
query ($userId: Int!, $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            hasNextPage
        }
        following (userId: $userId, sort: ID) {
            id
            name
        }
    }
}'''

    return depaginated_request(query=query_followed, variables={'userId': user_id})


def get_50_random_users():
    """"""
    # Pick a random page of users
    query_users = '''
query ($page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            lastPage
            hasNextPage
        }
        users (sort: ID) {
            id
            name
        }
    }
}
'''
    # Send a preliminary request to determine how many pages there are (hopefully won't decrease between requests...)
    response_data = safe_post_request({'query': query_users, 'variables': {'page': 1, 'perPage': MAX_PAGE_SIZE}})
    rand_page = random.randint(1, response_data['Page']['pageInfo']['lastPage'])

    # Fetch a random page and return its users
    response_data = safe_post_request({'query': query_users, 'variables': {'page': rand_page, 'perPage': MAX_PAGE_SIZE}})

    return response_data['Page']['users']


def matching_scores_count(scores_A, scores_B):
    """Given two dicts mapping AniList show IDs to scores, count how many shows both have scored within 0.5.
    Note that this means that a score of e.g. 7.5 will match both 7 and 8 in the case of comparing a decimal to a
    non-decimal-using user.
    """
    return sum(1 for show_id in scores_A.keys() & scores_B.keys()
               if -0.5 <= scores_A[show_id] - scores_B[show_id] <= 0.5)


def count_matching_nines(scores_A, scores_B):
    """Given two dicts mapping AniList show IDs to scores, count how many shows are a 9 or higher in both lists."""
    return sum(1 for show_id in scores_A.keys() & scores_B.keys()
               if scores_A[show_id] >= 9 and scores_B[show_id] >= 9)


def nines_trust(scores_A, scores_B):
    """Given two dicts mapping AniList show IDs to scores, of the shared shows, return what fraction of the 9+'s in the
    second list were also 9+'s in the first.
    """
    num_watched_nines = sum(1 for show_id in scores_A.keys() & scores_B.keys() if scores_B[show_id] >= 9)

    return count_matching_nines(scores_A, scores_B) / num_watched_nines if num_watched_nines != 0 else 0


def count_unseen_nines(scores_A, scores_B):
    return sum(1 for show_id in scores_B.keys() - scores_A.keys() if scores_B[show_id] >= 9)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Description of your program')
    parser.add_argument('username', help="Name of the anilist user to find similar users for.")
    args = parser.parse_args()

    # Fetch the target user's data
    target_user_id = get_user_id_from_name(args.username)
    target_completed_scores = get_user_completed_scores(target_user_id)

    # Get the users the target user is following
    followed_users = get_followed_users(target_user_id)

    # Find the followed user with the most matching scores
    max_nines_trust = 0
    max_trust_unseen_nines = 1
    max_trusted_username = None

    try:
        #while True:
        for user in followed_users:
            completed_scores = get_user_completed_scores(user['id'])
            num_matching_nines = count_matching_nines(target_completed_scores, completed_scores)
            num_unseen_nines = count_unseen_nines(target_completed_scores, completed_scores)
            nines_trust_val = nines_trust(target_completed_scores, completed_scores)

            if nines_trust_val >= 0.5 and num_matching_nines >= 3 and num_unseen_nines != 0:
                print(f"{user['name']} - {num_matching_nines} matching 9+'s ({int(nines_trust_val * 100)}% 9+'s trusted)")

            # Find the user whose 9+'s we trust the most and who has a non-zero number of 9+'s that we haven't seen.
            # Secondarily tiebreak by maximizing the number of 9s of theirs we haven't seen in case we do get to 100%
            if num_matching_nines >= 3 and ((nines_trust_val > max_nines_trust and num_unseen_nines != 0)
                    # Secondarily tiebreak by maximizing the number of 9s of theirs we haven't seen in case we do get to 100%
                    or (nines_trust_val == max_nines_trust and num_unseen_nines > max_trust_unseen_nines)):
                max_trusted_username = user['name']
                max_trust_unseen_nines = num_unseen_nines
                max_nines_trust = nines_trust_val
    except KeyboardInterrupt:
        print(f"{max_trusted_username} is the most trustworthy user found with {int(max_nines_trust * 100)}% of their 9+'s"
              f" trustworthy and {max_trust_unseen_nines} 9+'s {args.username} hasn't seen."
              f"\nhttps://anilist.co/user/{max_trusted_username}/animelist/compare")
