"""Common requests to the Anilist API.
See https://anilist.github.io/ApiV2-GraphQL-Docs/ and https://anilist.co/graphiql for help.
"""

from request_utils import safe_post_request, depaginated_request


def get_user_id_by_name(username: str):
    """Given an AniList username, fetch the user's ID."""
    query_user_id = '''
query ($username: String) {
    User (name: $username) { id }
}'''

    return safe_post_request({'query': query_user_id, 'variables': {'username': username}})['User']['id']


def get_user_media(user: str, status='COMPLETED'):
    """Given an AniList user ID, fetch their anime list, returning a list of media objects sorted by score (desc)."""
    query = '''
query ($userName: String, $status: MediaListStatus, $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo { hasNextPage }
        # Note that a MediaList object is actually a single list entry, hence the need for pagination
        # IMPORTANT: Always include MEDIA_ID in the sort, as the anilist API is bugged - if ties are possible,
        #            pagination can omit some results while duplicating others at the page borders.
        mediaList(userName: $userName, status: $status, sort: [SCORE_DESC, MEDIA_ID]) {
            media {
                id
                title {
                    english
                    romaji
                }
            }
        }
    }
}'''

    return [list_entry['media'] for list_entry in depaginated_request(query=query,
                                                                      variables={'userName': user, 'status': status})]
