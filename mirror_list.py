from typing import Optional, List
import json

import oauth
from request_utils import safe_post_request, depaginated_request
from upcoming_sequels import get_user_id_by_name


ALL_STATUSES = ('CURRENT', 'COMPLETED', 'PAUSED', 'DROPPED', 'PLANNING', 'REPEATING')
GLOBAL_FORCE = False

def mirror_list(from_user: str,
                to_user: str,
                status_map: dict[str, str],
                ignore_to_user_statuses: Optional[set[str]] = None,
                delete_unmapped: bool = True,
                clean: bool = False,
                collect_planning: bool = False,
                force: bool = False):
    """Update to_user's list to be a mirror of from_user's list, optionally with status remappings.
    status_map: A dict of {from_user_status: to_user_status}, where each such mapping will cause all list entries
        in from_user's list with status from_user_status to be copied to to_user's list, with the status
        updated to to_user_status.
        Valid statuses are: 'CURRENT', 'COMPLETED', 'PAUSED', 'DROPPED', 'PLANNING', 'REPEATING'.
        If not specified, fully mirrors from_user's list with all statuses self-mapping:
        {'CURRENT': 'CURRENT', 'COMPLETED': 'COMPLETED', ...} and so on.
    ignore_to_user_statuses: Statuses in to_user's list whose list entries should not be modified, regardless of
        their state in from_user's list.
        E.g. ignore_to_user_statuses={'PAUSED'} will not edit any entries in to_user's PAUSED list.
    delete_unmapped: If True, delete unmapped entries in to_user's list (excepting ignore_to_user_statuses entries,
        which are never modified). Default True.
    force: If True, do not prompt the user to confirm deletions or to verify entries whose statuses are changing.
        Default False.
    """
    def ask_for_confirm_or_skip():
        nonlocal force
        if force:
            return True

        confirm = input("Is this correct? y/n (stop the syncing process)/s (skip over this item and continue): ").strip().lower()
        if confirm == 'skip' or confirm == 's':
            return False
        elif confirm == 'n':
            raise Exception("User cancelled operation.")
        elif confirm == 'force':
            force = True
        elif confirm and not confirm.startswith('y'):
            ask_for_confirm_or_skip()

        return True

    # Make DAMN sure the user didn't mix up the --from and --to args.
    if not force and not input(f"{to_user}'s list will be modified. Is this correct? (y/n): ").strip().lower().startswith('y'):
        raise Exception("User cancelled operation.")

    if status_map is None:
        status_map = {status: status for status in ALL_STATUSES}

    # Case-sanitize inputs to reduce chance of footguns deleting users' hand-curated lists.
    status_map = {from_status.upper(): to_status.upper() for from_status, to_status in status_map.items()}
    ignore_to_user_statuses = set() if ignore_to_user_statuses is None else {status.upper() for status in ignore_to_user_statuses}

    from_user_list = get_user_list(from_user, status_in=tuple(status_map.keys()), use_oauth=(not collect_planning and not clean) or from_user == 'robert')

    # Fetch all of the --to user's list.
    to_user_list = get_user_list(to_user, use_oauth=True)
    to_user_list_by_media_id = {item['mediaId']: item for item in to_user_list}
    assert len(to_user_list) == len(to_user_list_by_media_id)  # Sanity check for multiple entries from one show

    # Get auth for mutating the second user's list
    to_user_oauth_token = oauth.get_oauth_token(to_user)

    for from_list_item in from_user_list:
        show_title = from_list_item['media']['title']['english'] or from_list_item['media']['title']['romaji']
        print(f'processing {show_title}')

        if clean:
            if from_list_item['mediaId'] in to_user_list_by_media_id:
                to_list_item = to_user_list_by_media_id[from_list_item['mediaId']]
                if to_list_item['status'] == 'PLANNING':
                    old_notes = to_list_item['notes'] if to_list_item['notes'] else ''
                    old_notes_split = [note for note in old_notes.split(', ') if note != from_user and note != '']
                    if len(old_notes_split) == 0 and ask_for_confirm_or_skip():
                        print('deleting', to_list_item)
                        delete_list_entry(to_list_item['id'], oauth_token=to_user_oauth_token)
                    else:
                        to_list_item['notes'] = ', '.join(old_notes_split)
                        to_list_item['customLists'] = [customList for customList in to_list_item['customLists'] if to_list_item['customLists'][customList]]
                        if old_notes != to_list_item['notes'] and ask_for_confirm_or_skip():
                            update_list_entry(to_list_item, oauth_token=to_user_oauth_token)
            continue

        # Remap the status (the status shouldn't be missing from the map since we used the map to fetch).
        from_list_item['status'] = status_map[from_list_item['status']]

        # Check if this is a new entry in the --to user's list.
        if from_list_item['mediaId'] not in to_user_list_by_media_id:
            print(f"`{show_title}` will be added to {from_list_item['status']}. ", end="")
            del from_list_item['customLists']
            del from_list_item['hiddenFromStatusLists']
            if collect_planning:
                notes = from_user.lower()
                if to_user == 'man' and from_user == 'robert':
                    # from_list_item['status'] = 'REPEATING'
                    from_list_item['hiddenFromStatusLists'] = True
                    from_list_item['customLists'] = ['Custom Planning List']
                    if from_list_item['media']['duration']:
                        notes = f"{from_list_item['media']['duration']} | {notes}"
                        if from_list_item['media']['duration'] < 20:
                            notes = f"#short {notes}"
                from_list_item['notes'] = notes
                from_list_item['score'] = 0
                from_list_item['progress'] = 0
                from_list_item['startedAt'] = {'year': None, 'month': None, 'day': None}
                from_list_item['completedAt'] = {'year': None, 'month': None, 'day': None}
            if ask_for_confirm_or_skip():
                with open("modifications.txt", "a+", encoding='utf8') as f:
                    f.write('adding ' + from_list_item['media']['title']['romaji'] + '\n')
                add_list_entry(from_list_item, oauth_token=to_user_oauth_token)
            continue

        # Otherwise, this is a mutation of an existing list entry
        to_list_item = to_user_list_by_media_id[from_list_item['mediaId']]
        if 'customLists' in to_list_item:
            from_list_item['customLists'] = [customList for customList in (to_list_item['customLists'] or []) if to_list_item['customLists'][customList]]
        else:
            from_list_item['customLists'] = []
        if collect_planning:
            if to_list_item['status'] in ('COMPLETED', 'CURRENT'):
                continue
            old_notes = to_list_item['notes'] if to_list_item['notes'] is not None else ''
            if from_user.lower() in old_notes.lower():
                new_notes = old_notes
            elif old_notes:
                new_notes = f'{old_notes}, {from_user.lower()}'
            else:
                new_notes = f'{from_user.lower()}'
            del from_list_item['hiddenFromStatusLists']
            if to_user == 'man':
                if from_user == 'robert' or 'robert' in old_notes:
                    # from_list_item['status'] = 'REPEATING'
                    from_list_item['hiddenFromStatusLists'] = True
                    from_list_item['customLists'] = from_list_item['customLists'] + (['Custom Planning List'] if 'Custom Planning List' not in from_list_item['customLists'] else [])
                    if not '|' in new_notes and from_list_item['media']['duration']:
                        new_notes = f"{from_list_item['media']['duration']} | {new_notes}"
                    if not '#short' in new_notes and from_list_item['media']['duration'] and from_list_item['media']['duration'] < 20:
                        new_notes = f"#short {new_notes}"
                else:
                    from_list_item['hiddenFromStatusLists'] = False
                    from_list_item['customLists'] = [customList for customList in from_list_item['customLists'] if customList != 'Custom Planning List']
            from_list_item['notes'] = new_notes
            from_list_item['status'] = 'PLANNING'
            from_list_item['score'] = 0
            from_list_item['progress'] = 0
            from_list_item['startedAt'] = {'year': None, 'month': None, 'day': None}
            from_list_item['completedAt'] = {'year': None, 'month': None, 'day': None}
        elif 'Custom Planning List' in (from_list_item['customLists'] or []) and to_list_item['status'] == 'PLANNING':
            from_list_item['hiddenFromStatusLists'] = False
            from_list_item['customLists'] = [customList for customList in from_list_item['customLists'] if customList != 'Custom Planning List']

        # Don't touch this entry if it's in a protected status list.
        if to_list_item['status'] in ignore_to_user_statuses:
            continue

        # Mutate the from_list_item's entry ID (different from media ID) to be that of the to_list_item.
        # This is smelly but simplifies the equality check and ensures that when we call update_list_entry with the
        # original entry to copy, it will have the correct entry ID.
        from_list_item['id'] = to_list_item['id']

        # the format for customLists retrieval is {'enabledCustomList': True, 'disabledCustomList': False}
        # the format for customLists write is ['enabledCustomList']
        # so to check equality we set it to be the same format
        to_list_item['customLists'] = [customList for customList in (to_list_item['customLists'] or []) if to_list_item['customLists'][customList]]

        # If the remapped list entry matches, there's nothing to update.
        if to_list_item == from_list_item:
            continue
        else:
            print('to', to_list_item)
            print('from', from_list_item)
            print('diff', {k: v for k, v in from_list_item.items() if from_list_item[k] != to_list_item[k]})
            with open("modifications.txt", "a+", encoding='utf8') as f:
                f.write(to_list_item['media']['title']['romaji'] + ' ' + json.dumps({k: str(to_list_item[k])+" -> "+str(v) for k, v in from_list_item.items() if from_list_item[k] != to_list_item[k]}) + '\n')

        # If the changes look major (status change or large change in score), ask user to confirm.
        if (from_list_item['status'] != to_list_item['status']
                or abs(from_list_item['score'] - to_list_item['score']) > 20):
            # Summarize the proposed updates and ask the user if they look okay
            print(f"\nProposed modification to existing entry for `{show_title}`:")
            for field in from_list_item.keys():
                if field != 'id' and field in to_list_item and to_list_item[field] != from_list_item[field]:
                    print(f"  {field}: {to_list_item[field]} -> {from_list_item[field]}")

            if not ask_for_confirm_or_skip():
                continue

        update_list_entry(from_list_item, oauth_token=to_user_oauth_token)

    # If deletions are enabled, delete any entries which weren't successfully mapped above.
    if not delete_unmapped:
        return

    mapped_media_ids = set(from_list_entry['mediaId'] for from_list_entry in from_user_list)  # Note that we only fetched mapped statuses.
    for to_list_item in to_user_list:
        if to_list_item['mediaId'] not in mapped_media_ids and to_list_item['status'] not in ignore_to_user_statuses:
            show_title = to_list_item['media']['title']['english'] or to_list_item['media']['title']['romaji']
            print(f"`{show_title}` will be deleted. ", end="")
            if ask_for_confirm_or_skip():
                delete_list_entry(entry_id=to_list_item['id'], oauth_token=to_user_oauth_token)


# Sorting on score makes mild sense here since those are the shows the user would first want to see in the list of
# proposed changes if the operation has bad changes.
def get_user_list(username: str, status_in: Optional[tuple] = None, use_oauth=False) -> list:
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
                duration
            }
            notes
            hiddenFromStatusLists
            customLists
        }
    }
}'''
    user_id = get_user_id_by_name(username)
    query_vars = {'userId': user_id}
    if status_in is not None:
        query_vars['statusIn'] = status_in  # AniList has magic to ignore parameters where the var is unprovided.

    # print(f'username {username} oauth {use_oauth}')
    oauth_token = None
    if use_oauth:
        try:
            oauth_token = oauth.get_oauth_token(username)
        except:
            pass

    return depaginated_request(query=query, variables=query_vars, oauth_token=oauth_token)


# Pretty sure this can be merged with update_list_entry using anilist magic per
# https://anilist.gitbook.io/anilist-apiv2-docs/overview/graphql/mutations but whatever.
def add_list_entry(list_entry: dict, oauth_token: str):
    """Given an anime ID, status, score, and started and completed dates, create or update the list entry for that
    media ID to match.
    """
    # Note the score -> scoreRaw variable change since Save's score var format is user-setting dependent whereas
    # the value returned from list queries is not.
    query = '''
mutation ($mediaId: Int, $status: MediaListStatus, $score: Int, $progress: Int, $startedAt: FuzzyDateInput, $completedAt: FuzzyDateInput, $notes: String, $hiddenFromStatusLists: Boolean, $customLists: [String]) {
    SaveMediaListEntry (mediaId: $mediaId, status: $status, scoreRaw: $score, progress: $progress, startedAt: $startedAt, completedAt: $completedAt, notes: $notes, hiddenFromStatusLists: $hiddenFromStatusLists, customLists: $customLists) {
        id  # The args are what update it so in theory we don't need any return values here.
    }
}
'''
    print('adding', list_entry['media']['title']['romaji'])
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
mutation ($id: Int, $mediaId: Int, $status: MediaListStatus, $score: Int, $progress: Int, $startedAt: FuzzyDateInput, $completedAt: FuzzyDateInput, $notes: String, $hiddenFromStatusLists: Boolean, $customLists: [String]) {
    SaveMediaListEntry (id: $id, mediaId: $mediaId, status: $status, scoreRaw: $score, progress: $progress, startedAt: $startedAt, completedAt: $completedAt, notes: $notes, hiddenFromStatusLists: $hiddenFromStatusLists, customLists: $customLists) {
        id  # The args are what update it so in theory we don't need any return values here.
    }
}
'''
    print('modifying', list_entry['media']['title']['romaji'])
    safe_post_request({'query': query, 'variables': list_entry}, oauth_token=oauth_token)


def delete_list_entry(entry_id: int, oauth_token: str):
    """Given an anime ID, delete its list entry."""
    query = '''
mutation ($id: Int) {
    DeleteMediaListEntry (id: $id) {
        deleted
    }
}
'''
    result = safe_post_request({'query': query, 'variables': {'id': entry_id}}, oauth_token=oauth_token)
    if not result['DeleteMediaListEntry']['deleted']:
        raise Exception("AniList API failed to delete list entry.")
