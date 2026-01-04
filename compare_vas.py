import argparse
from datetime import timedelta
from typing import Optional
import oauth
from request_utils import safe_post_request, depaginated_request, cache, dict_intersection, dict_diffs


@cache(".cache/staff_voice_roles.json", max_age=timedelta(days=30))
def get_voice_acting_roles(staff_id):
    """
    Returns { show_id: { title: "...", character: "...", role: "..." } }
    Always attempts to fetch `characterRole` and character details.
    """
    query = """
query ($id: Int, $page: Int, $perPage: Int) {
  Staff(id: $id) {
    characterMedia(sort: START_DATE_DESC, page: $page, perPage: $perPage) {
      pageInfo { hasNextPage }
      edges {
        node {
          id
          title { english romaji }
          startDate { year month day }
        }
        characterRole
        characters {
          name {
            full
          }
        }
      }
    }
  }
}
    """
    shows = {}

    for edge in depaginated_request(query=query, variables={"id": staff_id}):
        show = edge["node"]
        title = show["title"]["english"] or show["title"]["romaji"]
        character_role = edge["characterRole"]
        characters = [character["name"]["full"] for character in edge["characters"] if character]

        year = str(show["startDate"]["year"]).zfill(4) if show["startDate"]["year"] else '9999'
        month = str(show["startDate"]["month"]).zfill(2) if show["startDate"]["month"] else '99'
        day = str(show["startDate"]["day"]).zfill(2) if show["startDate"]["day"] else '99'
        startDate = year + month + day

        if show["id"] not in shows:
            shows[str(show["id"])] = {"title": title, "roles": [], "startDate": startDate}

        for character in characters:
            shows[str(show["id"])]["roles"].append(f"{character} ({character_role})")

    return shows


@cache(".cache/staff_production_roles.json", max_age=timedelta(days=30))
def get_staff_shows(staff_id):
    """
    Returns { show_id: { title: "...", roles: [ ... ] } }
    Always attempts to fetch `staffRole` field.
    """
    query = """
query ($id: Int, $page: Int, $perPage: Int) {
  Staff(id: $id) {
    staffMedia(type: ANIME, sort: START_DATE_DESC, page: $page, perPage: $perPage) {
      pageInfo { hasNextPage }
      edges {
        node {
          id
          title { english romaji }
          startDate { year month day }
        }
        staffRole  # Always include this field in the query
      }
    }
  }
}
    """
    shows = {}

    for edge in depaginated_request(query=query, variables={"id": staff_id}):
        show = edge["node"]
        title = show["title"]["english"] or show["title"]["romaji"]

        year = str(show["startDate"]["year"]).zfill(4) if show["startDate"]["year"] else '9999'
        month = str(show["startDate"]["month"]).zfill(2) if show["startDate"]["month"] else '99'
        day = str(show["startDate"]["day"]).zfill(2) if show["startDate"]["day"] else '99'
        startDate = year + month + day

        if show["id"] not in shows:
            shows[str(show["id"])] = {"title": title, "roles": [], "startDate": startDate}

        staff_role = edge.get("staffRole", "(role unavailable)")
        shows[str(show["id"])]["roles"].append(staff_role)

    return shows


@cache(".cache/staff_ids.json", max_age=timedelta(days=60))
def get_staff_id_by_name(name):
    """
    Given a staff name, return the AniList ID for the staff member, sorted by FAVOURITES.
    This version returns only the top staff result based on popularity (favorites).
    """
    query = """
query ($search: String) {
  Staff(search: $search, sort: FAVOURITES_DESC) {
    id
    name { full }
  }
}
    """
    try:
        # Perform the query to get staff by name, sorted by FAVOURITES
        result = safe_post_request({'query': query, 'variables': {'search': name}})

        # Check if the 'Staff' field is in the response and is not empty
        return result['Staff']['id']
    except Exception:
        raise Exception(f'Error while fetching staff_id for {name}')


def get_staff_names_by_ids(staff_ids):
    """
    Given a list of staff IDs, fetch the corresponding staff names from AniList.
    """
    query = """
query ($staffIds: [Int]) {
  Page {
    staff (id_in: $staffIds) {
      id
        name { full }
    }
  }
}
    """
    try:
        # Send the query with the list of staff IDs
        result = safe_post_request({'query': query, 'variables': {'staffIds': staff_ids}})
        staff_names = {}

        for staff in result['Page']['staff']:
            staff_names[staff['id']] = staff['name']['full']

        if len(staff_names) != len(staff_ids):
            raise Exception('Could not fetch name for all ids')
        return staff_names
    except Exception:
        raise Exception(f'Error while fetching staff_name for {staff_ids}')


@cache(".cache/user_list_vas.json", max_age=timedelta(minutes=15))
def get_user_list(username: str, status_in: Optional[tuple] = None, use_oauth: bool = False) -> list:
    """Given an AniList user ID, fetch the user's anime with given statuses, returning a list of show
     JSONs, including and sorted on score (desc).
     Include season and seasonYear.
     """
    query = '''
query ($userName: String, $statusIn: [MediaListStatus], $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            hasNextPage
        }
        # Note that a MediaList object is actually a single list entry, hence the need for pagination
        # IMPORTANT: Always include MEDIA_ID in the sort, as the anilist API is bugged - if ties are possible,
        #            pagination can omit some results while duplicating others at the page borders.
        mediaList(userName: $userName, type: ANIME, status_in: $statusIn, sort: [SCORE_DESC, MEDIA_ID]) {
            mediaId
            status
            score(format: POINT_100)  # Should be default format but just in case
            progress
            media {
                title {
                    english
                    romaji
                }
                duration
            }
        }
    }
}'''
    query_vars = {'userName': username}
    if status_in is not None:
        query_vars['statusIn'] = status_in  # AniList has magic to ignore parameters where the var is unprovided.

    oauth_token = None
    if use_oauth:
        try:
            oauth_token = oauth.get_oauth_token(username)
        except:
            pass

    return depaginated_request(query=query, variables=query_vars, oauth_token=oauth_token)


COL_SEP = 3
SHOW_COL_WIDTH = 50
STAFF_COL_WIDTH = 30


def print_row(cols, widths):
    print(
        (COL_SEP * " ").join(
            c[:w].ljust(w) for c, w in zip(cols, widths)
        )
    )


def main():
    parser = argparse.ArgumentParser(
        description="Compare anime that multiple staff members all appeared in."
    )
    parser.add_argument("staff", nargs="+", help="Staff names or IDs.")
    parser.add_argument("-i", "--ids", action="store_true", help="Input staff IDs instead of names.")
    parser.add_argument("-s", "--staff-role", action="store_true", help="Compare staff roles (default is voice acting roles).")
    parser.add_argument("-d", "--diff", action="store_true", help="Show differences instead of shared shows.")
    parser.add_argument("-r", "--reversed", action="store_true", help="Reverses the sort order of the show entries. (default newest first)")
    parser.add_argument("-u", "--username", help="An optional user whose list will be cross-referenced for appearances")
    parser.add_argument("-ur", "--username-reverse", help="An optional user whose list will be excluded for appearances")
    parser.add_argument("-m", "--main", action="store_true", help="Filter to only main roles")
    parser.add_argument("-l", "--show-length", help="Override show length displayed")
    parser.add_argument("-n", "--number-matches", help="Minimum number of shared cast (defaults to the whole list)")
    args = parser.parse_args()

    # Convert staff names to IDs if the `--ids` flag is set
    staff_ids = []
    if args.ids:
        # If IDs are provided, use them directly
        staff_ids = [int(s) for s in args.staff]
    else:
        # If names are provided, convert names to IDs
        for staff_name in args.staff:
            staff_ids.append(get_staff_id_by_name(staff_name))

    staff_names = get_staff_names_by_ids(staff_ids)

    print(f"Using the following staff names: {', '.join(staff_names.values())}")
    print("Fetching data...\n")

    # Retrieve shows for each staff
    if args.staff_role:
        # Compare staff roles
        lists = [get_staff_shows(sid) for sid in staff_ids]
    else:
        # Compare voice acting roles by default
        lists = [get_voice_acting_roles(sid) for sid in staff_ids]

    comparison_list = None
    if username := args.username or args.username_reverse:
        user_list = get_user_list(username, status_in=("CURRENT", "REPEATING", "COMPLETED", "PAUSED", "DROPPED"), use_oauth=username == 'robert')
        # comparison_list = dict([(str(media['mediaId']), 'WATCHED') for media in user_list])
        comparison_list = set([str(media['mediaId']) for media in user_list])

    if args.show_length:
        global SHOW_COL_WIDTH
        SHOW_COL_WIDTH = int(args.show_length)

    widths = [SHOW_COL_WIDTH] + [STAFF_COL_WIDTH] * len(staff_ids)
    print_row([""] + [staff_names[sid] for sid in staff_ids], widths)  # Display staff names

    # ----------------------------------
    # DIFF MODE
    # ----------------------------------
    if args.diff:
        diffs = dict_diffs(lists)

        print("\nShows unique to each staff:")
        for idx, unique_ids in enumerate(diffs):
            if not unique_ids:
                continue
            print(f"\nStaff {staff_names[staff_ids[idx]]}:\n" + "─" * 80)

            for show_id in unique_ids:
                title = lists[idx][show_id]["title"]
                roles = ", ".join(lists[idx][show_id]["roles"])
                print(f"  {title} [{roles}]")

        return

    # ----------------------------------
    # INTERSECTION MODE
    # ----------------------------------
    if args.main:
        # lists = [[entry for entry in sublist.valus() if any("(MAIN)" in role for role in entry["roles"])] for sublist in lists]
        lists = [{key: {**value, "roles": [role for role in value["roles"] if "(MAIN)" in role]}
                  for key, value in sublist.items() if any("(MAIN)" in role for role in value["roles"])}
                  for sublist in lists]

    if args.number_matches:
        args.number_matches = int(args.number_matches)

    shared_ids = dict_intersection(lists, args.number_matches)

    if comparison_list:
        shared_ids = list(set(shared_ids) & comparison_list) if args.username else list(set(shared_ids) - comparison_list)

    if not shared_ids:
        print(f"\n\nNo shared anime{' with main roles' if args.main else ''} between these staff.")
        return

    print("\nShared shows:")
    print("═" * (sum(widths) + COL_SEP * (len(widths) - 1)))

    show_titles_map = {show_id: lst[show_id]["title"] for lst in lists for show_id in lst}
    release_dates_map = {show_id: lst[show_id]["startDate"] for lst in lists for show_id in lst}

    # sort by startDate
    shared_ids = sorted(shared_ids, key=lambda show_id: release_dates_map[show_id], reverse=not args.reversed)

    for show_id in shared_ids:
        title = show_titles_map[show_id]
        max_roles = max(len(lst.get(show_id, {}).get("roles", [])) for lst in lists)

        for i in range(max_roles):
            row = [title if i == 0 else ""]
            for lst in lists:
                roles = lst.get(show_id, {}).get("roles", [])
                row.append(roles[i] if i < len(roles) else "")
            print_row(row, widths)

    print(f"\nTotal AniList API queries: {safe_post_request.total_queries}")


if __name__ == "__main__":
    main()
