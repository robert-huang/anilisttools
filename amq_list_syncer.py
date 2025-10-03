import argparse

from mirror_list import mirror_list
from request_utils import safe_post_request

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,  # Preserves newlines in description
        description="Given two anilist users, for any show:\n"
                    "* IN the --from user's (public) COMPLETED or WATCHING lists\n"
                    "* and NOT IN the --to user's PAUSED list\n"
                    "Copy the --from user's status/score/watch dates for that show, overwriting the --to user's list.")
    parser.add_argument('--from', dest="from_user", help="Username whose list should be copied from.")
    parser.add_argument('--to', dest="to_user", help="Username whose list should be modified.")
    parser.add_argument('--force', action='store_true', help="Do not ask for confirmation on changing show statuses.")
    parser.add_argument('--froms', nargs='*')
    group = parser.add_mutually_exclusive_group()
    parser.add_argument('--all', action='store_true')
    group.add_argument('-p', '--planning', action='store_true')
    group.add_argument('--clean', action='store_true')
    args = parser.parse_args()

    if args.all:
        status_map = {'CURRENT': 'CURRENT',
        'REPEATING': 'REPEATING',  # Note: AMQ treats REPEATING like COMPLETED.
        'COMPLETED': 'COMPLETED',
        # Remap to avoid the exclusionary paused list. We will assume for the CLI call that users
        # want songs from paused shows iff they want songs from dropped shows.
        # We also assume users don't want songs from their original planning list.
        'PAUSED': 'PAUSED',
        'DROPPED': 'DROPPED'}
    elif args.clean:
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

    mirror_list(from_users=[args.from_user, *args.froms],
                to_user = args.to_user,
                status_map = status_map,
                ignore_to_user_statuses={},
                delete_unmapped=True,  # Required to remove shows that moved back to the unmapped PLANNING.
                clean = args.clean,
                collect_planning = args.planning,
                force=args.force)

    print(f"\nTotal queries: {safe_post_request.total_queries}")
