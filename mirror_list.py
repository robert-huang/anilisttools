from typing import Callable, Optional
import json

import oauth
from request_utils import safe_post_request, depaginated_request
from upcoming_sequels import get_user_id_by_name


ALL_STATUSES = ('CURRENT', 'COMPLETED', 'PAUSED', 'DROPPED', 'PLANNING', 'REPEATING')
FORCE = False


def mirror_list(from_user: str, to_user: str,
                status_map: Optional[dict[str, str]] = None,
                ignore_to_user_statuses: Optional[set[str]] = None,
                delete_unmapped: bool = True,
                entry_factory: Optional[Callable] = None,
                verbose: bool = False,
                force: bool = True):
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
    entry_factory: An optional factory function that gets called once for each media ID (from_user_entry, to_user_entry)
                   pair, with either being None in the case of creates/deletes.
                   The function should return the final to_user entry that should be written, or None to delete it.
                   - If status_map is provided, from_user_entry's status will be post-transformation.
                     In the case that the from_user entry's status is unmapped (not a key of status_map):
                      - If delete_unmapped is True, entry_factory will be called with (None, to_user_entry) iff a to_user entry exists.
                      - If delete_unmapped is False, the call to entry_factory is skipped.
                   - If ignore_to_user_statuses is provided, the function will not be called if to_user_entry had an
                   ignored status.
    verbose: If True, print out summaries of all mutations made. Default False.
    force: If True, do not prompt the user to confirm deletions or to verify entries whose statuses are changing.
        Default True.
    """
    global FORCE
    FORCE = force

    # Make DAMN sure the user didn't mix up the from and to args.
    if not force and not input(f"{to_user}'s list will be modified. Is this correct? (y/n): ").strip().lower().startswith('y'):
        raise Exception("User cancelled operation.")

    if status_map is None:
        status_map = {status: status for status in ALL_STATUSES}

    # Case-sanitize inputs to reduce chance of footguns deleting users' hand-curated lists.
    status_map = {from_status.upper(): to_status.upper() for from_status, to_status in status_map.items()}
    ignore_to_user_statuses = set() if ignore_to_user_statuses is None else {status.upper() for status in ignore_to_user_statuses}

    # Get auth for mutating the second user's list
    to_user_oauth_token = oauth.get_oauth_token(to_user)

    # Fetch the lists.
    from_user_list = get_user_list(from_user, status_in=tuple(status_map.keys()), use_oauth=from_user == 'robert')
    mapped_media_ids = set(from_list_entry['mediaId'] for from_list_entry in from_user_list)
    to_user_list = get_user_list(to_user, use_oauth=True)  # Need all of to_user's list to detect any entry needing mutation.
    to_user_list_by_media_id = {item['mediaId']: item for item in to_user_list}
    assert len(to_user_list) == len(to_user_list_by_media_id)  # Sanity check for multiple entries from one show

    # Add or update entries we can map from from_user's list.
    for from_list_item in from_user_list:
        if verbose:
            show_title = from_list_item['media']['title']['english'] or from_list_item['media']['title']['romaji']
            print(f'processing {show_title}')

        # Remap the status (the status shouldn't be missing from the map since we used the map to fetch).
        from_list_item['status'] = status_map[from_list_item['status']]

        # Check if this is a new entry in the --to user's list.
        if from_list_item['mediaId'] not in to_user_list_by_media_id:
            # Apply any custom transformation.
            if entry_factory is not None:
                from_list_item = entry_factory(from_list_item, None)
                if from_list_item is None:
                    continue

            if confirm_entry_diff(old_entry=None, new_entry=from_list_item, verbose=verbose, force=force):
                if verbose:
                    print(f"`{show_title}` will be added to {from_list_item['status']}. ", end="")
                    with open("modifications.txt", "a+", encoding='utf8') as f:
                        f.write(f'adding {show_title}\n')
                add_list_entry(from_list_item, oauth_token=to_user_oauth_token, verbose=verbose)
            continue

        # Otherwise, this is a mutation of an existing list entry
        to_list_item = to_user_list_by_media_id[from_list_item['mediaId']]

        # Don't touch this entry if it's in a protected status list.
        if to_list_item['status'] in ignore_to_user_statuses:
            continue

        # Apply any custom transformation.
        if entry_factory is not None:
            from_list_item = entry_factory(from_list_item, to_list_item)

            if from_list_item is None:  # Switched to a delete.
                if confirm_entry_diff(old_entry=to_list_item, new_entry=None, verbose=verbose, force=force):
                    if verbose:
                        print(f"`{show_title}` will be deleted. ", end="")
                        with open("modifications.txt", "a+", encoding='utf8') as f:
                            f.write(f'deleting {show_title}\n')
                    delete_list_entry(entry_id=to_list_item['id'], oauth_token=to_user_oauth_token)
                continue

        # Mutate the from_list_item's entry ID (different from media ID) to be that of the to_list_item.
        # This is smelly but simplifies confirm_entry_diff's equality check and ensures that update_list_entry receives
        # the correct entry ID.
        from_list_item['id'] = to_list_item['id']

        if confirm_entry_diff(old_entry=to_list_item, new_entry=from_list_item, verbose=verbose, force=force):
            update_list_entry(from_list_item, oauth_token=to_user_oauth_token, verbose=verbose)

    # If deletions are enabled, delete any entries which weren't successfully mapped above.
    if not delete_unmapped:
        return

    for to_list_item in to_user_list:
        if to_list_item['mediaId'] in mapped_media_ids or to_list_item['status'] in ignore_to_user_statuses:
            continue

        # Give the custom transformer a chance to switch the deletion to a no-op or mutate.
        if entry_factory is not None:
            new_to_list_item = entry_factory(None, to_list_item)
            if new_to_list_item is not None:
                if confirm_entry_diff(old_entry=to_list_item, new_entry=new_to_list_item, verbose=verbose, force=force):
                    update_list_entry(new_to_list_item, oauth_token=to_user_oauth_token)
                continue

        if confirm_entry_diff(old_entry=to_list_item, new_entry=None, verbose=verbose, force=force):
            if verbose:
                print(f"`{show_title}` will be deleted. ", end="")
                with open("modifications.txt", "a+", encoding='utf8') as f:
                    f.write(f'deleting {show_title}\n')
            delete_list_entry(entry_id=to_list_item['id'], oauth_token=to_user_oauth_token)


# Sorting on score makes mild sense here since those are the shows the user would first want to see in the list of
# proposed changes if the operation has bad changes.
def get_user_list(username: str, status_in: Optional[tuple] = None, use_oauth: bool = False) -> list:
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
            notes
            hiddenFromStatusLists
            customLists
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

    oauth_token = None
    if use_oauth:
        try:
            oauth_token = oauth.get_oauth_token(username)
        except:
            pass

    return depaginated_request(query=query, variables=query_vars, oauth_token=oauth_token)


# Pretty sure this can be merged with update_list_entry using anilist magic per
# https://anilist.gitbook.io/anilist-apiv2-docs/overview/graphql/mutations but whatever.
def add_list_entry(list_entry: dict, oauth_token: str, verbose: bool = False):
    """Given an anime ID, status, score, and started and completed dates, create or update the list entry for that
    media ID to match.
    """
    # Note the score -> scoreRaw variable change since Save's score var format is user-setting dependent whereas
    # the value returned from list queries is not.
    query = '''
mutation ($mediaId: Int, $status: MediaListStatus, $score: Int, $progress: Int,
          $startedAt: FuzzyDateInput, $completedAt: FuzzyDateInput, $notes: String,
          $hiddenFromStatusLists: Boolean, $customLists: [String]) {
    SaveMediaListEntry (mediaId: $mediaId, status: $status, scoreRaw: $score, progress: $progress,
                        startedAt: $startedAt, completedAt: $completedAt, notes: $notes,
                        hiddenFromStatusLists: $hiddenFromStatusLists, customLists: $customLists) {
        id  # The args are what update it so in theory we don't need any return values here.
    }
}
'''
    if verbose:
        print('adding', list_entry['media']['title']['romaji'])
    query_vars = {k: v for k, v in list_entry.items() if k != 'id'}
    # AniList has an inconsistency where customLists are returned as bool dicts but only work when set as lists.
    if 'customLists' in list_entry and isinstance(list_entry['customLists'], dict):
        query_vars['customLists'] = [k for k, v in list_entry['customLists'].items() if v]

    safe_post_request({'query': query, 'variables': query_vars}, oauth_token=oauth_token)


# See https://anilist.gitbook.io/anilist-apiv2-docs/overview/graphql/mutations
def update_list_entry(list_entry: dict, oauth_token: str, verbose: bool = False):
    """Given an anime ID, status, score, and started and completed dates, create or update the list entry for that
    media ID to match.
    """
    # Note the score -> scoreRaw variable change since Save's score var format is user-setting dependent whereas
    # the value returned from list queries is not.
    query = '''
mutation ($id: Int, $mediaId: Int, $status: MediaListStatus, $score: Int, $progress: Int,
          $startedAt: FuzzyDateInput, $completedAt: FuzzyDateInput, $notes: String,
          $hiddenFromStatusLists: Boolean, $customLists: [String]) {
    SaveMediaListEntry (id: $id, mediaId: $mediaId, status: $status, scoreRaw: $score, progress: $progress,
                        startedAt: $startedAt, completedAt: $completedAt, notes: $notes,
                        hiddenFromStatusLists: $hiddenFromStatusLists, customLists: $customLists) {
        id  # The args are what update it so in theory we don't need any return values here.
    }
}
'''
    if verbose:
        print('modifying', list_entry['media']['title']['romaji'])
    query_vars = list_entry
    # AniList has an inconsistency where customLists are returned as bool dicts but only work when set as lists.
    if 'customLists' in list_entry and isinstance(list_entry['customLists'], dict):
        query_vars = {k: v for k, v in list_entry.items()}
        query_vars['customLists'] = [k for k, v in list_entry['customLists'].items() if v]

    safe_post_request({'query': query, 'variables': query_vars}, oauth_token=oauth_token)


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


def ask_for_confirm_or_skip():
    global FORCE
    if FORCE:
        return True

    confirm = input("Is this correct? y/n (stop the syncing process)/s (skip over this item and continue): ").strip().lower()
    if confirm == 'skip' or confirm == 's':
        return False
    elif confirm == 'n':
        raise Exception("User cancelled operation.")
    elif confirm == 'force':
        FORCE = True
    elif confirm and not confirm.startswith('y'):
        ask_for_confirm_or_skip()

    return True


def confirm_entry_diff(old_entry: Optional[dict], new_entry: Optional[dict], verbose=True, force=False):
    """Helper to print a description of a create, update, or delete to a media entry, and ask for user confirmation in
    all cases except a 'minor' update (doesn't change the status and only touches 1-2 fields).
    Returns False if no diff exists or if the user rejected the change. Raises an error if they quit out.
    """
    if new_entry == old_entry:
        return False
    if force and not verbose:
        return True

    if verbose:
        print('to', old_entry)
        print('from', new_entry)
        if old_entry and new_entry:
            print('diff', {k: v for k, v in new_entry.items() if new_entry[k] != old_entry[k]})
            with open("modifications.txt", "a+", encoding='utf8') as f:
                f.write(old_entry['media']['title']['romaji'] + ' ' + json.dumps({k: str(old_entry[k])+" -> "+str(v) for k, v in new_entry.items() if new_entry[k] != old_entry[k]}) + '\n')

    show_title = (old_entry or new_entry)['media']['title']['english'] or (old_entry or new_entry)['media']['title']['romaji']

    major_change = True
    if old_entry is None:
        description = f"Adding `{show_title}` to {new_entry['status']}. "
    elif new_entry is None:
        description = f"`Deleting {show_title}`. "
    else:
        diff_fields = [field for field in old_entry.keys() | new_entry.keys()
                       if old_entry.get(field) != new_entry.get(field)]
        major_change = old_entry['status'] != new_entry['status'] or len(diff_fields) >= 3
        description = f"Modifying existing entry for `{show_title}`:"
        for field in diff_fields:
             description += f"\n  {field}: {old_entry.get(field)} -> {new_entry.get(field)}"

    print(description)

    return force or (not major_change) or ask_for_confirm_or_skip()