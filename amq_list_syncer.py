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
    parser.add_argument('--to', dest="to_user", help="Username whose list should be modified.")
    parser.add_argument('--force', action='store_true',
                        help="Do not ask for confirmation on changing show statuses. Turn on at your own risk.")
    parser.add_argument('--froms', nargs='*')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-p', '--planning', action='store_true')
    group.add_argument('--clean', action='store_true')
    args = parser.parse_args()

    if args.clean:
        # checks if the entry has moved from planning to a different list on the from_user's list
        # doesn't work if the from_user simply removed it from their planning list
        status_map = {'CURRENT': 'CURRENT',
                      'COMPLETED': 'COMPLETED',
                      'REPEATING': 'REPEATING',
                      'DROPPED': 'DROPPED'}
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

    for from_user in from_users:
        print(f"----processing {from_user}'s list----")
        if not from_user:
            continue

        mirror_list(from_user = from_user,
                    to_user = args.to_user,
                    status_map = status_map,
                    ignore_to_user_statuses={},
                    delete_unmapped=False,  # Required to remove shows that moved back to the unmapped PLANNING.
                    clean = args.clean,
                    collect_planning = args.planning,
                    force=args.force)

    print(f"\nTotal queries: {safe_post_request.total_queries}")
