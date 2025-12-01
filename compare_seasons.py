"""Given an anilist username, and two anime seasons, compare the user's completed/watching from each, by score."""

import argparse
from datetime import timedelta
from itertools import chain

from request_utils import cache, safe_post_request, depaginated_request


# TODO: Use MediaListCollection to get 500 entries at a time instead of 50
# TODO: Proper object-oriented library with e.g. User.shows(fields=[...])
@cache(".cache/user_list_seasons.json", max_age=timedelta(minutes=15))
def get_user_shows(username, status_in=('COMPLETED',)) -> list:
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
            media {
                id
                title {
                    english
                    romaji
                }
                season
                seasonYear
            }
            score
        }
    }
}'''

    return [{**list_entry['media'], 'score': list_entry['score']}  # Stuff score in too
            for list_entry in depaginated_request(query=query, variables={'userName': username, 'statusIn': status_in})]

# python.exe compare_seasons.py robert -l 40 "winter 2020" "spring 2020" "summer 2020" "fall 2020" "winter 2021" "spring 2021" "summer 2021" "fall 2021" "winter 2022" "spring 2022" "summer 2022" "fall 2022" "winter 2023" "spring 2023" "summer 2023" "fall 2023" "winter 2024" "spring 2024" "summer 2024" "fall 2024" "winter 2025" "spring 2025" "summer 2025" "fall 2025" "winter 2026" "spring 2026" "summer 2026" "fall 2026" > seasons.txt
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Given an AniList username, check what shows from their completed or planning lists have known\n"
                    "upcoming seasons.",
        formatter_class=argparse.RawTextHelpFormatter)  # Preserves newlines in help text
    parser.add_argument('username', help="User whose list should be checked.")
    parser.add_argument('seasons', nargs='+',
                        help='Seasons or years to compare, formatted as e.g. 2021 or "Winter 2021".\n'
                             'Seasons are Winter, Spring, Summer, Fall.')
    parser.add_argument("-l", "--show-length", help="Override show length displayed")
    parser.add_argument("-s", "--skip-empty", action="store_true", help="Skip empty years/seasons")
    args = parser.parse_args()

    user_shows = get_user_shows(args.username, status_in=('COMPLETED', 'CURRENT', 'REPEATING'))

    if args.seasons == ['all']:
        args.seasons = [str(year) for year in range(min([show['seasonYear'] if show['seasonYear'] else 9999 for show in user_shows]),
                                                    max([show['seasonYear'] if show['seasonYear'] else 0 for show in user_shows]) + 1)]
    elif args.seasons == ['allseasons']:
        args.seasons = list(chain.from_iterable([[f"winter {year}", f"spring {year}", f"summer {year}", f"fall {year}"]
                                                 for year in range(min([show['seasonYear'] if show['seasonYear'] else 9999 for show in user_shows]),
                                                                   max([show['seasonYear'] if show['seasonYear'] else 0 for show in user_shows]) + 1)]))

    # Pick out the user's watching/completed anime from each season and their scores
    seasonal_user_shows = []
    for season_str in args.seasons:
        *season, year = season_str.split()  # Handle both "year" and "season year"
        year = int(year)
        if season:
            season = season[0].upper()

        # Note that the user list is already sorted by score so this will be too
        season_user_shows = [show for show in user_shows
                             if show['seasonYear'] == year and (show['season'] == season or not season)]
        seasonal_user_shows.append(season_user_shows)

    # Printout the info
    def pad(s, width):
        return str(s)[:width].ljust(width)

    DISPLAY_LENGTH = int(args.show_length) if args.show_length else 30
    def display_season(lst):
        if args.skip_empty:
            return len(lst) > 0
        else:
            return True

    print('   '.join([pad(season, DISPLAY_LENGTH) for i, season in enumerate(args.seasons) if display_season(seasonal_user_shows[i])]))
    print('   '.join([pad('     avg: ' + str(round(sum([show['score'] for show in shows]) / len(shows), 3)  if len(shows) > 0 else "N/A"), DISPLAY_LENGTH)
                      for shows in seasonal_user_shows if display_season(shows)]))
    print("=" * ((DISPLAY_LENGTH + 3) * len([shows for shows in seasonal_user_shows if display_season(shows)]) - 3))
    for i in range(max(len(shows) for shows in seasonal_user_shows)):
        print('   '.join(pad(shows[i]['score'], 3) + '  ' + pad(shows[i]['title']['english']
                                                                or shows[i]['title']['romaji'], (DISPLAY_LENGTH - 5))
                         if i < len(shows) else DISPLAY_LENGTH * ' '
                         for shows in seasonal_user_shows if display_season(shows)))

    print(f"\nTotal queries: {safe_post_request.total_queries}")
