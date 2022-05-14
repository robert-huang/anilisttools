import argparse

from utils import safe_post_request, depaginated_request

COL_WIDTH = 40
COL_SEP = 10


# Ideally we could sort on [SEARCH_MATCH, POPULARITY_DESC], but this doesn't seem to work as expected in the case of
# shows with the exact same title (e.g. Golden Time); the less popular one is still returned.
def get_show(search, sort_by="SEARCH_MATCH"):
    """Given an approximate show name, return the closest-matching show with ID and title.
    Default sorts by closeness of the string match. Use e.g. POPULARITY_DESC for cases where shows share a name (e.g.
    "Golden Time" will by default return the one no one cares about).
    """
    query = '''
query ($search: String, $sort: MediaSort) {
    Media(search: $search, type: ANIME, sort: [$sort]) {
        id
        title {
            english
            romaji
        }
    }
}'''
    result = safe_post_request({'query': query, 'variables': {'search': search, 'sort': sort_by}})
    if result is not None:
        result = result['Media']

        # In case a show has no english title, fall back to romaji
        title = result['title']['english'] if result['title']['english'] is not None else result['title']['romaji']
        assert title is not None, f"API returned an untitled show for \"{search}\" (show ID: {result['id']})"

        result = {'id': result['id'], 'title': title}

    return result


def get_show_studios(show_id):
    """Given a show ID, return a dict of its studios, formatted as id: {"name": "...", "roles": ["..."]}."""
    query = '''
query ($mediaId: Int) {
    Media(id: $mediaId) {
        studios {
            edges {
                node {
                    id
                    name
                }
                isMain
            }
        }
    }
}'''
    # Since the API doesn't sort by isMain, handle main vs supporting studios separately so we can return main
    # studio(s) at the front of the results
    main_studios_dict = {}
    supporting_studios_dict = {}

    # the Media.studios API also does not seem to be paginated even though StudioConnection has pageInfo
    for edge in safe_post_request({'query': query, 'variables': {'mediaId': show_id}})['Media']['studios']['edges']:
        if edge['isMain']:
            main_studios_dict[edge['node']['id']] = {'name': edge['node']['name'], 'roles': ["Main"]}
        else:
            supporting_studios_dict[edge['node']['id']] = {'name': edge['node']['name'], 'roles': ["Supporting"]}

    return main_studios_dict | supporting_studios_dict


def get_show_production_staff(show_id):
    """Given a show ID, return a dict of its production staff, formatted as id: {"name": "...", "roles": ["..."]}."""
    query = '''
query ($mediaId: Int, $page: Int, $perPage: Int) {
    Media(id: $mediaId) {
        staff(sort: RELEVANCE, page: $page, perPage: $perPage) {
            pageInfo {
                hasNextPage
            }
            # Direct `nodes` field is also available, but it includes duplicates per edge (e.g. one staff with two roles
            # shows up twice), so avoiding it to keep things intuitive.
            edges {
                node {
                    id
                    name {
                        full
                    }
                }
                role
            }
        }
    }
}'''
    staff_dict = {}

    for edge in depaginated_request(query=query, variables={'mediaId': show_id}):
        # Account for staff potentially having multiple roles
        if edge['node']['id'] not in staff_dict:
            staff_dict[edge['node']['id']] = {'name': edge['node']['name']['full'],
                                              'roles': []}

        staff_dict[edge['node']['id']]['roles'].append(edge['role'])

    return staff_dict


def get_show_voice_actors(show_id, language="JAPANESE"):
    """Given a show ID, return a dict of its voice actors for the given language (default: "JAPANESE"), formatted as:
    id: {"name": "...", "roles": ["MAIN: Edward Elric", "SUPPORTING: Edward Elric (child)"]}.
    """
    query = '''
query ($mediaId: Int, $language: StaffLanguage, $page: Int, $perPage: Int) {
    Media(id: $mediaId) {
        characters(sort: [ROLE, RELEVANCE], page: $page, perPage: $perPage) {
            pageInfo {
                hasNextPage
            }
            edges {
                node {  # Character
                    name {
                        full
                    }
                }
                role  # MAIN, SUPPORTING, or BACKGROUND
                voiceActorRoles(language: $language) {  # This is a list, but the API doesn't make us paginate it
                    voiceActor {
                        id
                        name {
                            full
                        }
                    }
                    roleNotes
                }
            }
        }
    }
}'''
    vas_dict = {}

    for edge in depaginated_request(query=query, variables={'mediaId': show_id, 'language': language}):
        for va_role in edge['voiceActorRoles']:
            # Account for VAs potentially having multiple roles
            if va_role['voiceActor']['id'] not in vas_dict:
                vas_dict[va_role['voiceActor']['id']] = {'name': va_role['voiceActor']['name']['full'],
                                                         'roles': []}

            role_descr = edge['role'] + " " + edge['node']['name']['full']
            if va_role['roleNotes'] is not None:
                role_descr += " " + va_role['roleNotes']

            vas_dict[va_role['voiceActor']['id']]['roles'].append(role_descr)

    return vas_dict


def dict_intersection(dicts):
    """Given an iterable of dicts, return a list of the intersection of their keys, while preserving the order of the
    keys from the first given dict."""

    dicts = list(dicts)  # Avoid gotchas if we were given an iterator
    if not dicts:
        return []

    return [k for k in dicts[0] if all(k in d for d in dicts[1:])]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Find all studios/staff/VAs common to the given shows.")
    parser.add_argument('shows', nargs='+', help="Shows to compare.")
    parser.add_argument('-s', '--sort', default='SEARCH_MATCH',
                        help="How to sort shows when matching the given query parmeter."
                             "\nDefault uses closest string match; for certain shows that share a name (e.g. Golden "
                             "\nTime), you may need to use e.g. --sort=POPULARITY_DESC to match the right one."
                             "\nSee MediaSort in https://anilist.github.io/ApiV2-GraphQL-Docs/ for more options.")
    args = parser.parse_args()

    # TODO: If given one show, search through its staff to find the shows that share the most staff with it, or the
    #       most 'key' staff (e.g. weight VAs lower, directors higher, give original creator their own section)
    assert len(args.shows) > 1, "Please specify 2 or more shows"

    show_titles = []
    show_studios_dicts = []
    show_production_staff_dicts = []
    show_voice_actors_dicts = []

    # Lookup each show by name
    for show in args.shows:
        show_data = get_show(show, sort_by=args.sort)
        if show_data is None:
            raise ValueError(f"Could not find show matching {show}")

        show_titles.append(show_data['title'])
        show_studios_dicts.append(get_show_studios(show_data['id']))
        show_production_staff_dicts.append(get_show_production_staff(show_data['id']))
        show_voice_actors_dicts.append(get_show_voice_actors(show_data['id'], language="JAPANESE"))

    # Pretty-print a column-wise comparison of the shows and their common staff
    total_width = (COL_WIDTH + COL_SEP) * len(args.shows) - COL_SEP

    def col_print(items):
        print((COL_SEP * ' ').join(item[:COL_WIDTH].center(COL_WIDTH) for item in items))

    col_print(show_titles)

    # List common studios/staff, sectioned separately by studios vs production staff vs voice actors
    common_found = False
    for staff_type, show_staff_dicts in [["Studios", show_studios_dicts],
                                         ["Production Staff", show_production_staff_dicts],
                                         ["Voice Actors (JP)", show_voice_actors_dicts]]:
        # Find the common staff between the shows. Use a helper to avoid sets so that dict ordering is maintained
        common_staff_ids = dict_intersection(show_staff_dicts)

        if common_staff_ids:
            common_found = True
            print("")
            print("")
            print("═" * total_width)
            print(staff_type.center(total_width))
            print("═" * total_width)

            for staff_id in common_staff_ids:
                # Print the staff name center-justified
                print(show_staff_dicts[0][staff_id]['name'].center(total_width))

                # Print the list of roles that the staff had in each show
                max_roles = max(len(show_staff[staff_id]['roles']) for show_staff in show_staff_dicts)
                for i in range(max_roles):
                    col_print(show_staff[staff_id]['roles'][i] for show_staff in show_staff_dicts
                              if i < len(show_staff[staff_id]['roles']))

                print("_" * total_width)

    if not common_found:
        print("")
        print("No common studios/staff/VAs found!".center(total_width))
