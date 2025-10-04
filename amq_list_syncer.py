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
    parser.add_argument('--from', dest="from_user", required=True, help="Username whose list should be copied from.")
    parser.add_argument('--to', dest="to_user", required=True, help="Username whose list should be modified.")
    parser.add_argument('--force', action='store_true',
                        help="Do not ask for confirmation on creates, deletes, or Watch Status edits. Turn on at your own risk.")
    args = parser.parse_args()

    mirror_list(from_user=args.from_user, to_user=args.to_user,
                status_map={'CURRENT': 'CURRENT',
                            'REPEATING': 'REPEATING',  # Note: AMQ treats REPEATING like COMPLETED.
                            'COMPLETED': 'COMPLETED',
                            # Remap to avoid the exclusionary paused list. We will assume for the CLI call that users
                            # want songs from paused shows iff they want songs from dropped shows.
                            # We also assume users don't want songs from their original planning list.
                            'PAUSED': 'DROPPED',
                            'DROPPED': 'DROPPED'},
                # Treat the to_user's PAUSED and PLANNING as hand-crafted special lists not to be touched.
                # This frees up PAUSED to be a force-exclude and PLANNING to be a force-include.
                ignore_to_user_statuses={'PAUSED', 'PLANNING'},
                delete_unmapped=True,  # Required to remove shows that moved back to the unmapped PLANNING.
                force=args.force)

    print(f"\nTotal queries: {safe_post_request.total_queries}")
