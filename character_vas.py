import argparse
from datetime import timedelta
import math
import json

from request_utils import safe_post_request, depaginated_request, cache
from anilist_utils import get_user_id_by_name, get_user_media


TOP_N = 20

def get_favorite_characters(username: str):
    """Given an anilist username, return the IDs of their favorite characters, in order."""
    query_user_favorite_characters = '''
query ($username: String, $page: Int, $perPage: Int) {
    User(name: $username) {
        favourites {
            characters(page: $page, perPage: $perPage) {
                pageInfo { hasNextPage }
                nodes {  # Character
                    id
                    name {
                        full
                        native
                    }
                }
            }
        }
    }
}'''

    return depaginated_request(query=query_user_favorite_characters, variables={'username': username})


@cache('.cache/character_vas.json', max_age=timedelta(days=90))  # Cache for one anime season
def get_character_vas_raw(char_id: int):
    """Return VAs for a given character. Separated from get_character_vas to avoid caching based on the media
    filter.
    """
    query = '''
query ($id: Int, $page: Int, $perPage: Int) {
    Character(id: $id) {
        media(page: $page, perPage: $perPage) {  # MediaConnection
            pageInfo { hasNextPage }
            edges {  # MediaEdge
                node { id }  # Media (note: node must be included or the query breaks; we need it anyway).
                voiceActors(language: JAPANESE, sort: RELEVANCE) {  # Staff
                    id
                    name { full }
                }
            }
        }
    }
}'''
    return depaginated_request(query=query, variables={'id': char_id})


def get_character_vas(char_id: int, media: set):
    """Return VAs for a given character, ignoring media not in the given set (e.g. if VA changes in a later unwatched
     season).
     Note that there may be multiple VAs even excluding dubs.
     """
    # De-dupe and return only the voiceActor(s) part of each edge.
    va_ids = set()
    vas = []
    for response in get_character_vas_raw(char_id):
        # Ignore media the user hasn't seen. E.g. if a character's VA changed.
        if response['node']['id'] not in media:
            continue

        for va in response['voiceActors']:
            if va['id'] not in va_ids:
                vas.append(va)
                va_ids.add(va['id'])

    return vas


@cache('.cache/va_characters.json', max_age=timedelta(days=90))  # Cache for one anime season
def get_va_characters_raw(va_id: int):
    """Return characters voiced by a given VA. Separated from get_va_characters to avoid caching based on the media
    filter.
    """
    query = '''
query ($id: Int, $page: Int, $perPage: Int) {
    Staff(id: $id) {
        characterMedia(page: $page, perPage: $perPage) {  # MediaConnection
            pageInfo { hasNextPage }
            edges {  # MediaEdge
                # For some reason including the Media node is required or else voiceActors ends up null.
                node { id }  # Media (note: node must be included or the query breaks; we need it anyway).
                characters { id }  # Character
            }
        }
    }
}'''
    return depaginated_request(query=query, variables={'id': va_id})


def get_va_characters(va_id: int, media: set):
    """Return characters voiced by a given VA, restricted to the given set of media IDs.
     Note that there may be multiple characters per media.
     """
    # De-dupe and return only the character(s) part of each edge.
    character_ids = set()
    characters = []
    for response in get_va_characters_raw(va_id):
        # Ignore media the user hasn't seen. E.g. if a character's VA changed.
        if response['node']['id'] not in media:
            continue

        for character in response['characters']:
            # There's a bug or something in the API where certain characters have a duplicate null result included.
            # E.g. When querying staff 95337, Nichijou appears twice, once with character 42697 and once with null.
            # Possibly affects all characters with digits or other special characters in their name, but also affects
            # e.g. GTO character 34121 with simply a 4-word name, so not totally sure.
            if character is None:
                continue

            if character['id'] not in character_ids:
                characters.append(character)
                character_ids.add(character['id'])

    return characters


def main():
    parser = argparse.ArgumentParser(
        description="Given an anilist username, find VAs with the most and highest-ranked favorited characters.",
        formatter_class=argparse.RawTextHelpFormatter)  # Preserves newlines in help text
    parser.add_argument('username', help="User whose list should be checked.")
    parser.add_argument('-f', '--file', help='optional parameter to output the results of the query')
    args = parser.parse_args()

    user_id = get_user_id_by_name(args.username)
    completed_ids = set(media['id'] for media in get_user_media(user_id, status='COMPLETED'))
    characters = get_favorite_characters(args.username)  # Ordered

    if len(characters) > 50:  # Only takes 1 request per character to find their VAs
        print(f"Checking VAs for {len(characters)} favorited characters, this will take a few minutes for first run...")

    va_names = {}  # Store all dicts by ID not name since names can collide.
    va_counts = {}
    va_rank_sums = {}
    va_roles = {}
    va_roles_rank = {}

    for i, character in enumerate(characters):
        # Search all VAs for this character and count them
        for va in get_character_vas(character['id'], media=completed_ids):
            va_names[va['id']] = va['name']['full']
            va_counts[va['id']] = va_counts.setdefault(va['id'], 0) + 1
            va_rank_sums[va['id']] = va_rank_sums.setdefault(va['id'], 0) + i + 1  # 1-index for rank
            va_roles.setdefault(va['id'], []).append(character['name']['native'])
            va_roles_rank.setdefault(va['id'], []).append(f"{character['name']['native']} ({i+1})")

    va_avg_ranks = {va_id: va_rank_sums[va_id] / va_counts[va_id] for va_id in va_names}

    # Count how many unique characters of a particular VA the user has seen
    va_total_char_counts = {va_id: len(get_va_characters(va_id, media=completed_ids)) for va_id in va_names}

    print(f"\nTop {TOP_N} VAs by fav character count")
    print("═════════════════════════════════")
    for va_id, va_count in sorted(va_counts.items(), key=lambda x: x[1], reverse=True)[:TOP_N]:
        print(f"{va_count:2} | {va_names[va_id][:20]}")

    print(f"\nTop {TOP_N} VAs by avg fav char rank (min 2)")
    print("═══════════════════════════════════════")
    for va_id, va_avg_rank in sorted(va_avg_ranks.items(),
                                     # De-prioritize VAs the user has only favorited once
                                     key=lambda x: x[1] if va_counts[x[0]] > 1 else math.inf)[:TOP_N]:
        print(f"{va_avg_rank:.1f} | {va_names[va_id][:20]}")

    # Yes, this probably biases against prolific VAs.
    print(f"\nTop {TOP_N} VAs by % of their characters favorited (min 2)")
    print("═════════════════════════════════════════════════════")
    for _id in sorted(va_names.keys(),
                      key=lambda _id: (va_counts[_id] / va_total_char_counts[_id]
                                       # De-prioritize VAs the user has only favorited once
                                       - (va_counts[_id] <= 1)),
                      reverse=True)[:TOP_N]:
        percent_favorited = 100 * (va_counts[_id] / va_total_char_counts[_id])
        print(f"{int(percent_favorited)}% ({va_counts[_id]}/{va_total_char_counts[_id]}) | {va_names[_id][:20]}")

    print(f"\nTotal queries: {safe_post_request.total_queries} (non-user-specific data cached)")

    if args.file:
        with open(args.file, 'w', encoding='utf8') as f:
            for va_id, va_count in sorted(va_counts.items(), key=lambda x: x[1], reverse=True):
                f.write(f"{va_count} | {va_names[va_id]}\n")
                f.write(f"\t{', '.join(va_roles[va_id])}\n")
            f.write('\n\n\n')
            for va_id, va_avg_rank in sorted(va_avg_ranks.items(),
                                             # De-prioritize VAs the user has only favorited once
                                             key=lambda x: x[1] if va_counts[x[0]] > 1 else math.inf):
                f.write(f"{va_avg_rank:.1f} | {va_names[va_id]}\n")
                f.write(f"\t{', '.join(va_roles_rank[va_id])}\n")
            f.write('\n\n\n')
            for _id in sorted(va_names.keys(),
                              key=lambda _id: (va_counts[_id] / va_total_char_counts[_id]
                                               # De-prioritize VAs the user has only favorited once
                                               - (va_counts[_id] <= 1)),
                              reverse=True):
                percent_favorited = 100 * (va_counts[_id] / va_total_char_counts[_id])
                f.write(f"{percent_favorited:.1f}% ({va_counts[_id]}/{va_total_char_counts[_id]}) | {va_names[_id]}\n")


if __name__ == '__main__':
    main()
