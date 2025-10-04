import argparse

from mirror_list import mirror_list
from request_utils import safe_post_request


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,  # Preserves newlines in description
        description="Given two AniList users, mirror anime entries from --from user's list to --to user's list, according\n"
                    "to the following mapping of watch statuses:\n"
                    "* CURRENT -> CURRENT, COMPLETED -> COMPLETED, REPEATING -> REPEATING, DROPPED -> DROPPED\n"
                    "* PAUSED -> DROPPED\n"
                    "* PLANNING -> not copied\n"
                    "* Delete entries of --to user's list that couldn't be mapped from --from user's list.\n"
                    "* EXCEPTION: Entries in --to user's PLANNING and PAUSED lists are never edited nor deleted.\n"
                    "\n"
                    "TL;DR the --to user's PLANNING / PAUSED lists are reserved for custom AMQ adds/removes respectively,\n"
                    "and otherwise the --from user's non-planning entries are mirrored over as best as possible.")
    parser.add_argument('--from', dest="from_user", help="Username whose list should be copied from.")
    parser.add_argument('--to', dest="to_user", help="Username whose list should be modified.", required=True)
    parser.add_argument('--force', action='store_true',
                        help="Do not ask for confirmation on creates, deletes, or Watch Status edits. Turn on at your own risk.")
    parser.add_argument('--froms', nargs='*')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-p', '--planning', action='store_true')
    group.add_argument('--clean', action='store_true')
    args = parser.parse_args()

    if args.clean:
        # checks if the entry has moved from planning to a different list on the from_user's list
        # doesn't work if the from_user simply removed it from their planning list
        status_map = {'CURRENT': 'PLANNING',
                      'COMPLETED': 'PLANNING',
                      'REPEATING': 'PLANNING',
                      'PAUSED': 'PLANNING',
                      'DROPPED': 'PLANNING'}
    elif args.planning:
        status_map = {'PLANNING': 'PLANNING'}
    else:
        status_map = {'CURRENT': 'CURRENT',
                      'COMPLETED': 'COMPLETED',
                      'REPEATING': 'REPEATING'}

    from_users=[user for user in [args.from_user, *args.froms] if user]

    if len(from_users) > 1 and not args.planning and not input(f"Copying the completed/current lists of {from_users} to {args.to_user}. Is this correct? (y/n): ").strip().lower().startswith('y'):
        raise Exception("User cancelled operation.")

    with open("modifications.txt", "w", encoding='utf8') as f:
        f.write(f"to_user: {args.to_user}\nfrom_users: {from_users}\n\n")

    def entry_factory_robert(from_list_item: dict, to_list_item: dict):
        # if to_list_item is None, this is a new entry
        if to_list_item is None:
            if args.clean: # any entry not already on the target list can be ignored
                return None
            del from_list_item['customLists']
            del from_list_item['hiddenFromStatusLists']
            if args.planning:
                notes = from_user.lower()
                if args.to_user == 'man' and from_user == 'robert':
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
            return from_list_item
        # if from_list_item is None, that means this exists only in target, return old to_list_item to no-op
        elif from_list_item is None:
            return to_list_item
        else: # both exist, mutation
            if args.clean:
                if to_list_item['status'] == 'PLANNING':
                    old_notes = to_list_item['notes'] if to_list_item['notes'] else ''
                    old_notes_split = [note for note in old_notes.split(', ') if note != from_user and note != '']
                    if len(old_notes_split) == 0:
                        return None
                    else:
                        from_list_item = to_list_item.copy()
                        from_list_item['notes'] = ', '.join(old_notes_split)
                        return from_list_item
                else: # already on my own list as not planning, return old to_list_item to no-op
                    return to_list_item
            if 'customLists' in to_list_item:
                from_list_item['customLists'] = to_list_item['customLists'] or {}
            else:
                del from_list_item['customLists']
            if args.planning:
                if to_list_item['status'] in ('COMPLETED', 'CURRENT', 'REPEATING'):
                    # return old to_list_item to no-op
                    return to_list_item
                del from_list_item['hiddenFromStatusLists']
                if args.to_user == 'man':
                    old_notes = to_list_item['notes'] if to_list_item['notes'] is not None else ''
                    if from_user.lower() in old_notes.lower():
                        new_notes = old_notes
                    elif old_notes:
                        new_notes = f'{old_notes}, {from_user.lower()}'
                    else:
                        new_notes = f'{from_user.lower()}'
                    if from_user == 'robert' or 'robert' in old_notes:
                        from_list_item['hiddenFromStatusLists'] = True
                        from_list_item['customLists']['Custom Planning List'] = True
                        if not '|' in new_notes and from_list_item['media']['duration']:
                            new_notes = f"{from_list_item['media']['duration']} | {new_notes}"
                        if not '#short' in new_notes and from_list_item['media']['duration'] and from_list_item['media']['duration'] < 20:
                            new_notes = f"#short {new_notes}"
                    else:
                        from_list_item['hiddenFromStatusLists'] = False
                        from_list_item['customLists']['Custom Planning List'] = False
                    from_list_item['notes'] = new_notes
                from_list_item['status'] = 'PLANNING'
                from_list_item['score'] = 0
                from_list_item['progress'] = 0
                from_list_item['startedAt'] = {'year': None, 'month': None, 'day': None}
                from_list_item['completedAt'] = {'year': None, 'month': None, 'day': None}
            elif 'customLists' in from_list_item and 'Custom Planning List' in from_list_item['customLists'] and to_list_item['status'] == 'PLANNING':
                from_list_item['hiddenFromStatusLists'] = False
                from_list_item['customLists']['Custom Planning List'] = False
            return from_list_item


    for from_user in from_users:
        print(f"----processing {from_user}'s list----")

        mirror_list(from_user=from_user,
                    to_user=args.to_user,
                    status_map=status_map,
                    ignore_to_user_statuses=set(),
                    delete_unmapped=False,  # Required to remove shows that moved back to the unmapped PLANNING.
                    entry_factory=entry_factory_robert,
                    verbose=True,
                    force=args.force)

    print(f"\nTotal queries: {safe_post_request.total_queries}")