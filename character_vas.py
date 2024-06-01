import argparse
from datetime import timedelta
import math
import json
from enum import IntEnum

from request_utils import safe_post_request, depaginated_request, cache
from anilist_utils import get_user_id_by_name


def get_favorite_vas(username: str):
    """Given an anilist username, return the IDs of their favorite VAs, in order."""
    query_user_favorite_characters = '''
query ($username: String, $page: Int, $perPage: Int) {
    User(name: $username) {
        favourites {
            staff(page: $page, perPage: $perPage) {
                pageInfo { hasNextPage }
                nodes {  # Character
                    id
                    name {
                        full
                        native
                    }
                    gender
                }
            }
        }
    }
}'''

    return depaginated_request(query=query_user_favorite_characters, variables={'username': username})


def get_user_consumed_media_ids(user_id):
    """Given an AniList user ID, fetch their anime list, returning a list of media objects sorted by score (desc)."""
    query = '''
query ($userId: Int, $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo { hasNextPage }
        # Note that a MediaList object is actually a single list entry, hence the need for pagination
        # IMPORTANT: Always include MEDIA_ID in the sort, as the anilist API is bugged - if ties are possible,
        #            pagination can omit some results while duplicating others at the page borders.
        mediaList(userId: $userId, status_not: PLANNING, sort: [MEDIA_ID]) {
            mediaId
        }
    }
}'''

    return [list_entry['mediaId'] for list_entry in depaginated_request(query=query, variables={'userId': user_id})]


TOP_N = 20
DUMMY_MEDIAN_DATA_POINTS = 5

class CharacterRole(IntEnum):
    MAIN = 0
    SUPPORTING = 1
    BACKGROUND = 2

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
                    gender
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
                node {  # Media (note: node must be included or the query breaks; we need it anyway).
                    id
                    title {  # MediaTitle
                        romaji
                        native
                    }
                    type
                    format
                }
                characterRole
                voiceActors(language: JAPANESE, sort: RELEVANCE) {  # Staff
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
    return depaginated_request(query=query, variables={'id': char_id})


def get_character_vas(char_id: int, media: set, char_name: str, shows, books):
    """Return VAs for a given character, ignoring media not in the given set (e.g. if VA changes in a later unwatched
     season).
     Note that there may be multiple VAs even excluding dubs.
     """
    # De-dupe and return only the voiceActor(s) part of each edge.
    va_ids = set()
    vas = []
    char_role = 3
    seen = False
    is_main = False
    for response in get_character_vas_raw(char_id):
        # Ignore media the user hasn't seen. E.g. if a character's VA changed.
        if response['node']['id'] not in media:
            continue
        else:
            title = response['node']['title']['native'] if response['node']['title']['native'] and not ENGLISH_FLAG else response['node']['title']['romaji']
            type = response['node']['type']
            if type == 'ANIME':
                if title in shows:
                    shows[title].add(char_name)
                else:
                    shows[title] = {char_name}
            elif type == 'MANGA':
                if title in books:
                    books[title].add(char_name)
                else:
                    books[title] = {char_name}

        # Count a character as their highest role tier.
        char_role = min(char_role, int(CharacterRole[response['characterRole']]))
        seen = True

        # Count a character as main if they're main in at least one show.
        is_main |= response['characterRole'] == 'MAIN'

        for va in response['voiceActors']:
            if va['id'] not in va_ids:
                vas.append(va)
                va_ids.add(va['id'])

    return char_role, seen, is_main, vas, shows, books


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
    parser.add_argument('-e', '--english', action='store_true', help='optional parameter to use english character names not native')
    args = parser.parse_args()

    global ENGLISH_FLAG
    ENGLISH_FLAG = args.english

    user_id = get_user_id_by_name(args.username)
    consumed_media_ids = set(get_user_consumed_media_ids(user_id))
    characters = get_favorite_characters(args.username)  # Ordered
    fav_vas = get_favorite_vas(args.username)  # Ordered

    DUMMY_MEDIAN_DATA_POINTS = len(characters)/20

    if len(characters) > 50:  # Only takes 1 request per character to find their VAs
        print(f"Checking VAs for {len(characters)} favorited characters, this will take a few minutes for first run...")

    va_names = {}  # Store all dicts by ID not name since names can collide.
    va_counts = {}
    va_rank_sums = {}
    va_roles = {}
    va_roles_rank = {}
    char_gender = {'male': [], 'female': [], 'other': []}
    char_role_tier = [[], [], [], []]
    num_seen = 0  # Num favorited chars for which the user has consumed at least one media.
                  # For example they might have video game chars favorited for whom they've not seen any anime.
    num_main = 0  # Num chars that are MAIN in at least one media the user has seen/read.
    shows = {}
    books = {}

    for i, character in enumerate(characters):
        # Search all VAs for this character and count them
        char_name = character['name']['native'] if character['name']['native'] and not ENGLISH_FLAG else character['name']['full']

        # Also check if this character is a main character in any show while we're at it
        char_role, seen, is_main, vas, shows, books = get_character_vas(character['id'], media=consumed_media_ids, char_name=char_name, shows=shows, books=books)
        char_role_tier[char_role].append(char_name)

        gender = str(character['gender']).lower()
        char_gender[gender if gender in ['male', 'female'] else 'other'].append(char_name)

        num_seen += seen
        num_main += is_main

        for va in vas:
            va_names[va['id']] = va['name']['full']
            # add DUMMY_MEDIAN_DATA_POINTS dummy data points at median rank
            va_counts[va['id']] = va_counts.setdefault(va['id'], DUMMY_MEDIAN_DATA_POINTS) + 1
            va_rank_sums[va['id']] = va_rank_sums.setdefault(va['id'], len(characters)/2*DUMMY_MEDIAN_DATA_POINTS) + i + 1  # 1-index for rank
            va_roles.setdefault(va['id'], []).append(char_name)
            va_roles_rank.setdefault(va['id'], []).append(f"{char_name} ({i+1})")

    va_avg_ranks = {va_id: va_rank_sums[va_id] / va_counts[va_id] for va_id in va_names}

    # Count how many unique characters of a particular VA the user has seen
    va_total_char_counts = {va_id: len(get_va_characters(va_id, media=consumed_media_ids)) for va_id in va_names}

    print(f"\nTop {TOP_N} VAs by fav character count")
    print("═════════════════════════════════")
    for va_id, va_count in sorted(va_counts.items(), key=lambda x: x[1], reverse=True)[:TOP_N]:
        print(f"{(va_count-DUMMY_MEDIAN_DATA_POINTS)} | {va_names[va_id][:20]}")

    print(f"\nTop {TOP_N} VAs by avg fav char rank")
    print("═══════════════════════════════════════")
    for va_id, va_avg_rank in sorted(va_avg_ranks.items(), key=lambda x: x[1])[:TOP_N]:
        print(f"{va_avg_rank:.1f} | {va_names[va_id][:20]}")

    # Yes, this probably biases against prolific VAs.
    print(f"\nTop {TOP_N} VAs by % of their characters favorited (min 2)")
    print("═════════════════════════════════════════════════════")
    for _id in sorted(va_names.keys(),
                      key=lambda _id: ((va_counts[_id]-DUMMY_MEDIAN_DATA_POINTS) / (va_total_char_counts[_id]+len(characters)/10)),
                      reverse=True)[:TOP_N]:
        percent_favorited = 100 * ((va_counts[_id]-DUMMY_MEDIAN_DATA_POINTS) / va_total_char_counts[_id])
        print(f"{int(percent_favorited)}% ({va_counts[_id]-DUMMY_MEDIAN_DATA_POINTS}/{va_total_char_counts[_id]}) | {va_names[_id][:20]}")

    print(f"{len(char_gender['female'])} female characters, {len(char_gender['male'])} male characters, {len(char_gender['other'])} others.")

    print(f"\n% main chars: {round(100 * (len(char_role_tier[CharacterRole.MAIN]) / num_seen))}%")
    print(f"\n% supporting chars: {round(100 * (len(char_role_tier[CharacterRole.SUPPORTING]) / num_seen))}%")
    print(f"\n% background chars: {round(100 * (len(char_role_tier[CharacterRole.BACKGROUND]) / num_seen))}%")

    print(f"\nTotal queries: {safe_post_request.total_queries} (non-user-specific data cached)")

    if args.file:
        with open(args.file, 'w', encoding='utf8') as f:
            for va_id, va_count in sorted(va_counts.items(), key=lambda x: x[1], reverse=True):
                f.write(f"{va_count-DUMMY_MEDIAN_DATA_POINTS} | {va_names[va_id]}\n")
                f.write(f"\t{', '.join(va_roles[va_id])}\n")
            f.write('\n\n\n')
            for va_id, va_avg_rank in sorted(va_avg_ranks.items(), key=lambda x: x[1]):
                f.write(f"{va_avg_rank:.1f} | {va_names[va_id]}\n")
                f.write(f"\t{', '.join(va_roles_rank[va_id])}\n")
            f.write('\n\n\n')
            for _id in sorted(va_names.keys(),
                              key=lambda _id: ((va_counts[_id]-DUMMY_MEDIAN_DATA_POINTS) / (va_total_char_counts[_id]+len(characters)/10)),
                              reverse=True):
                percent_favorited = 100 * ((va_counts[_id]-DUMMY_MEDIAN_DATA_POINTS) / va_total_char_counts[_id])
                f.write(f"{percent_favorited:.1f}% ({va_counts[_id]-DUMMY_MEDIAN_DATA_POINTS}/{va_total_char_counts[_id]}) | {va_names[_id]}\n")
            f.write('\n\n\n')
            f.write(f"{len(char_gender['female'])} female characters ({round(100 * (len(char_gender['female']) / num_seen))}%), {len(char_gender['male'])} male characters ({round(100 * (len(char_gender['male']) / num_seen))}%), {len(char_gender['other'])} others ({round(100 * (len(char_gender['other']) / num_seen))}%).\n\n")
            f.write(f"Female: {', '.join(char_gender['female'])}\n\nMale: {', '.join(char_gender['male'])}\n\nOther (agender or missing data): {', '.join(char_gender['other'])}\n")
            f.write('\n\n\n')
            f.write(f"{len(char_role_tier[CharacterRole.MAIN])} main characters ({round(100 * (len(char_role_tier[CharacterRole.MAIN]) / num_seen))}%), {len(char_role_tier[CharacterRole.SUPPORTING])} supporting characters ({round(100 * (len(char_role_tier[CharacterRole.SUPPORTING]) / num_seen))}%), {len(char_role_tier[CharacterRole.BACKGROUND])} background characters ({round(100 * (len(char_role_tier[CharacterRole.BACKGROUND]) / num_seen))}%).\n\n")
            f.write(f"Main: {', '.join(char_role_tier[CharacterRole.MAIN])}\n\nSupporting: {', '.join(char_role_tier[CharacterRole.SUPPORTING])}\n\nBackground: {', '.join(char_role_tier[CharacterRole.BACKGROUND])}\n\nUnknown: {', '.join(char_role_tier[3])}\n")

            f.write('\n\n\n')
            f.write('{\n\t"ANIME": {\n\t\t')
            f.write(',\n\t\t'.join([f"'{key}': {value}" for key, value in shows.items()]))
            f.write('\n\t}, \n\t"MANGA": {\n\t\t')
            f.write(',\n\t\t'.join([f"'{key}': {value}" for key, value in books.items()]))
            f.write('\n\t}\n}')

            f.write('\n\n\nVAs: ')
            f.write(', '.join([va['name']['native'] if (va['name']['native'] and not ENGLISH_FLAG) else va['name']['full'] for va in fav_vas]))
            f.write('\n\nFemale: ')
            f.write(', '.join([va['name']['native'] if (va['name']['native'] and not ENGLISH_FLAG) else va['name']['full'] for va in [va for va in fav_vas if va['gender'] == 'Female']]))
            f.write('\n\nMale: ')
            f.write(', '.join([va['name']['native'] if (va['name']['native'] and not ENGLISH_FLAG) else va['name']['full'] for va in [va for va in fav_vas if va['gender'] == 'Male']]))
            f.write('\n\nUnknown: ')
            f.write(', '.join([va['name']['native'] if (va['name']['native'] and not ENGLISH_FLAG) else va['name']['full'] for va in [va for va in fav_vas if va['gender'] != 'Male' and va['gender'] != 'Female']]))

if __name__ == '__main__':
    main()
