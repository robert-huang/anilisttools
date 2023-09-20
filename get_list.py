import argparse
from enum import Enum
from msilib.schema import Media
from types import NoneType
from typing import Optional

from upcoming_sequels import get_user_id_by_name
from request_utils import depaginated_request

class MediaType(Enum):
    MatchAll = 'ALL'
    Anime = 'ANIME'
    Manga = 'MANGA'

class MediaStatus(Enum):
    MatchAll = 'ALL'
    Watching = 'CURRENT'
    Planning = 'PLANNING'
    Completed = 'COMPLETED'
    Dropped = 'DROPPED'
    Paused = 'PAUSED'
    Rewatching = 'REPEATING'

QUERY_SPECIFIC_TYPE_AND_STATUS = '''
query ($userId: Int, $type: MediaType, $status: MediaListStatus, $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            hasNextPage
        }
        # Note that a MediaList object is actually a single list entry, hence the need for pagination
        mediaList(userId: $userId, type: $type, status: $status, sort: MEDIA_ID) {
            media {
                id
                title {
                    english
                    romaji
                }
                type
                format
                episodes
            }
            score
            status
            progress
            repeat
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
            updatedAt
            notes
            hiddenFromStatusLists
            customLists
        }
    }
}'''

QUERY_SPECIFIC_TYPE = '''
query ($userId: Int, $type: MediaType, $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            hasNextPage
        }
        # Note that a MediaList object is actually a single list entry, hence the need for pagination
        mediaList(userId: $userId, type: $type, sort: MEDIA_ID) {
            media {
                id
                title {
                    english
                    romaji
                }
                type
                format
                episodes
            }
            score
            status
            progress
            repeat
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
            updatedAt
            notes
            hiddenFromStatusLists
            customLists
        }
    }
}'''

QUERY_SPECIFIC_STATUS = '''
query ($userId: Int, $status: MediaListStatus, $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            hasNextPage
        }
        # Note that a MediaList object is actually a single list entry, hence the need for pagination
        mediaList(userId: $userId, status: $status, sort: MEDIA_ID) {
            media {
                id
                title {
                    english
                    romaji
                }
                type
                format
                episodes
            }
            score
            status
            progress
            repeat
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
            updatedAt
            notes
            hiddenFromStatusLists
            customLists
        }
    }
}'''

QUERY_RETURN_ALL = '''
query ($userId: Int, $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            hasNextPage
        }
        # Note that a MediaList object is actually a single list entry, hence the need for pagination
        mediaList(userId: $userId, sort: MEDIA_ID) {
            media {
                id
                title {
                    english
                    romaji
                }
                type
                format
                episodes
            }
            score
            status
            progress
            repeat
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
            updatedAt
            notes
            hiddenFromStatusLists
            customLists
        }
    }
}'''


def get_user_media(user_id: int,
                   status: Optional[MediaStatus]=None,
                   type: Optional[MediaType]=None) -> list[dict]:
    """Given an AniList user ID, fetch the user's anime list, returning a list of shows and details."""
    if status is not None and type is not None:
        return [list_entry for list_entry in depaginated_request(query=QUERY_SPECIFIC_TYPE_AND_STATUS,
                                                                 variables={'userId': user_id, 'type': type.value, 'status': status.value})]
    elif status is not None:
        return [list_entry for list_entry in depaginated_request(query=QUERY_SPECIFIC_STATUS,
                                                                 variables={'userId': user_id, 'status': status.value})]
    elif type is not None:
        return [list_entry for list_entry in depaginated_request(query=QUERY_SPECIFIC_TYPE,
                                                                 variables={'userId': user_id, 'type': type.value})]
    else:
        return [list_entry for list_entry in depaginated_request(query=QUERY_RETURN_ALL,
                                                                 variables={'userId': user_id})]

def main(username: str, file: str):
    user_id = get_user_id_by_name(username)
    user_media_list = get_user_media(user_id, type=MediaType.Anime, status=MediaStatus.Completed)
    user_media_list.sort(key=lambda x: float(x['score']), reverse=True)
    if file:
        with open(file, 'w', encoding='utf-8') as f:
            for i in range(len(user_media_list)):
                entry = user_media_list[i]
                if i > 0:
                    last_entry = user_media_list[i-1]
                    if entry['score'] != last_entry['score']:
                        f.write(f"{entry['score']}\n")
                f.write(f"{entry['media']['title']['romaji']} ({entry['media']['format']})\n")
    else:
        for entry in user_media_list:
            print(f"{entry['media']['title']['english'] if entry['media']['title']['english'] else entry['media']['title']['romaji']} ({entry['media']['format']})")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Given an anilist username, print all the shows they have completed on Anilist.",
        formatter_class=argparse.RawTextHelpFormatter)  # Preserves newlines in help text
    parser.add_argument('-u', '--username', required=True,
                        help="User whose list should be checked.")
    parser.add_argument('-f', '--file', required=False, default=None,
                        help="File to write the output to.")
    args = parser.parse_args()

    main(args.username, args.file)
