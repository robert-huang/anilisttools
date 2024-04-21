import argparse

import oauth
from request_utils import safe_post_request, depaginated_request
from upcoming_sequels import get_user_id_by_name


# Sorting on score makes mild sense here since those are the shows the user would first want to see in the list of
# proposed changes if the operation has bad changes.
def get_user_list(user_id, status_in=None) -> list:
    """Given an AniList user ID, fetch the user's anime with given statuses, returning a list of show
     JSONs, including and sorted on score (desc).
     Include season and seasonYear.
     """
    query = '''
query ($userId: Int, $statusIn: [MediaListStatus], $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            hasNextPage
        }
        # Note that a MediaList object is actually a single list entry, hence the need for pagination
        # IMPORTANT: Always include MEDIA_ID in the sort, as the anilist API is bugged - if ties are possible,
        #            pagination can omit some results while duplicating others at the page borders.
        mediaList(userId: $userId, type: ANIME, status_in: $statusIn, sort: [SCORE_DESC, MEDIA_ID]) {
            id  # ID of the list entry itself
            mediaId
            status
            score(format: POINT_100)  # Should be default format but just in case
            progress
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
            media {
                title {
                    english
                    romaji
                }
            }
        }
    }
}'''
    query_vars = {'userId': user_id}
    if status_in is not None:
        query_vars['statusIn'] = status_in  # AniList has magic to ignore parameters where the var is unprovided.

    return depaginated_request(query=query, variables=query_vars)


# Pretty sure this can be merged with update_list_entry using anilist magic per
# https://anilist.gitbook.io/anilist-apiv2-docs/overview/graphql/mutations but whatever.
def add_list_entry(list_entry: dict, oauth_token: str):
    """Given an anime ID, status, score, and started and completed dates, create or update the list entry for that
    media ID to match.
    """
    # Note the score -> scoreRaw variable change since Save's score var format is user-setting dependent whereas
    # the value returned from list queries is not.
    query = '''
mutation ($mediaId: Int, $status: MediaListStatus, $score: Int, $progress: Int,
          $startedAt: FuzzyDateInput, $completedAt: FuzzyDateInput) {
    SaveMediaListEntry (mediaId: $mediaId, status: $status, scoreRaw: $score, progress: $progress,
                        startedAt: $startedAt, completedAt: $completedAt) {
        id  # The args are what update it so in theory we don't need any return values here.
    }
}
'''
    safe_post_request({'query': query, 'variables': {k: v for k, v in list_entry.items() if k != 'id'}},
                      oauth_token=oauth_token)


# See https://anilist.gitbook.io/anilist-apiv2-docs/overview/graphql/mutations
def update_list_entry(list_entry: dict, oauth_token: str):
    """Given an anime ID, status, score, and started and completed dates, create or update the list entry for that
    media ID to match.
    """
    # Note the score -> scoreRaw variable change since Save's score var format is user-setting dependent whereas
    # the value returned from list queries is not.
    query = '''
mutation ($id: Int, $mediaId: Int, $status: MediaListStatus, $score: Int, $progress: Int,
          $startedAt: FuzzyDateInput, $completedAt: FuzzyDateInput) {
    SaveMediaListEntry (id: $id, mediaId: $mediaId, status: $status, scoreRaw: $score, progress: $progress,
                        startedAt: $startedAt, completedAt: $completedAt) {
        id  # The args are what update it so in theory we don't need any return values here.
    }
}
'''
    safe_post_request({'query': query, 'variables': list_entry}, oauth_token=oauth_token)


def ask_for_confirm_or_skip():
    if args.force:
        return True

    confirm = input("Is this correct? (y/n/skip): ").strip().lower()
    if confirm == 'skip':
        return False
    elif not confirm.startswith('y'):
        raise Exception("User cancelled operation.")

    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,  # Preserves newlines in description
        description="Given two anilist users, for any show:\n"
                    "* IN the --from user's (public) COMPLETED or WATCHING lists\n"
                    "* and NOT IN the --to user's PAUSED list\n"
                    "Copy the --from user's status/score/watch dates for that show, overwriting the --to user's list.")
    parser.add_argument('--from', dest="from_user", help="Username whose list should be copied from.")
    parser.add_argument('--to', dest="to_user", help="Username whose list should be modified.")
    parser.add_argument('--force', help="Do not ask for confirmation on changing show statuses.")
    parser.add_argument('--except', dest='excepted', nargs='+', help="Show ID numbers to ignore.")
    args = parser.parse_args()

    ignored_media_ids = set(int(x) for x in args.excepted) if args.excepted else set()

    # Make DAMN sure the user didn't mix up the --from and --to args.
    if not args.force and not input(f"{args.to_user}'s list will be modified. Is this correct? (y/n): ").strip().lower().startswith('y'):
        raise Exception("User cancelled operation.")

    # Fetch the --from user's completed/watching shows.
    # TODO: Probably want to detect if anything moved from Watching -> Paused or Dropped, too
    from_user_id = get_user_id_by_name(args.from_user)
    from_user_list = get_user_list(from_user_id, status_in=('COMPLETED', 'CURRENT'))
    from_user_list_by_media_id = {item['mediaId']: item for item in from_user_list}
    assert len(from_user_list) == len(from_user_list_by_media_id)  # Sanity check for multiple entries from one show

    # Fetch all of the --to user's list.
    to_user_id = get_user_id_by_name(args.to_user)
    to_user_list = get_user_list(to_user_id)
    to_user_list_by_media_id = {item['mediaId']: item for item in to_user_list}
    assert len(to_user_list) == len(to_user_list_by_media_id)  # Sanity check for multiple entries from one show

    # Get auth for mutating the second user's list
    to_user_oauth_token = oauth.get_oauth_token(args.to_user)

    show_ids_to_add_entries_for = []
    list_ids_to_mutate = []
    for from_list_item in from_user_list:
        show_title = from_list_item['media']['title']['english'] or from_list_item['media']['title']['romaji']

        if from_list_item['mediaId'] in ignored_media_ids:
            continue

        # Check if this is a new entry for the --to user's list.
        if from_list_item['mediaId'] not in to_user_list_by_media_id:
            print(f"`{show_title}` will be added. ", end="")
            if ask_for_confirm_or_skip():
                add_list_entry(from_list_item, oauth_token=to_user_oauth_token)
            continue

        # Otherwise, this is a mutation of an existing list entry
        to_list_item = to_user_list_by_media_id[from_list_item['mediaId']]

        # The Paused list functions as the 'don't update me' list.
        if to_list_item['status'] == 'PAUSED':
            continue

        # Mutate the from_list_item's 'id' to be that of the to_list_item. This both simplifies the below check and
        # ensures that when we call update_list_entry with the entry to copy, it will have the relevant entry ID.
        from_list_item['id'] = to_list_item['id']

        # Check if the list entries match (other than the list entry IDs themselves).
        if to_list_item == from_list_item:
            continue

        # If the changes look major (status change or large change in score), ask user to confirm.
        if (from_list_item['status'] != to_list_item['status']
                or abs(from_list_item['score'] - to_list_item['score']) > 20):
            # Summarize the proposed updates and ask the user if they look okay
            print(f"\nProposed modification to existing entry for `{show_title}`:")
            for field in from_list_item.keys():
                if field != 'id' and to_list_item[field] != from_list_item[field]:
                    print(f"  {field}: {to_list_item[field]} -> {from_list_item[field]}")

            if not ask_for_confirm_or_skip():
                continue

        update_list_entry(from_list_item, oauth_token=to_user_oauth_token)

    print(f"\nTotal queries: {safe_post_request.total_queries}")
