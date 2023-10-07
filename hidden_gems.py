"""Fetch anime below a certain popularity and above a certain score."""

import argparse
from typing import Optional

from request_utils import safe_post_request, depaginated_request


# TODO: Allow passing a user, and use their personal scores instead of average score (to get shows *they* would consider
#       hidden gems).
# Other unmitigated sources of bias: anime age - longer time to gain popularity and increasing number of users per year.
def get_hidden_gems(popularity=50_000, score=80, max_count=None) -> list:
    """Given popularity and score cutoffs, return all anime that are below the given popularity and
    above the given (average) score. Default <= 50,000 popularity and >= 80 score.

    To account for sequel bias, halves the popularity limit and increases the min score by 1 for anime that are sequels.

    Pass max_count to limit results length.
    """
    # First, query the full popularity limit with only base seasons included
    query = '''
query ($score: Int, $popularity: Int, $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo { hasNextPage }
        # IMPORTANT: Always include ID in the sort, as the anilist API is bugged - if ties are possible,
        #            pagination can omit some results while duplicating others at the page borders.
        media(type: ANIME, format: TV, averageScore_greater: $score, popularity_lesser: $popularity, 
              # Not sure the secondary pop. sort does anything; there may be an internal fine-grained score order.
              sort: [SCORE_DESC, POPULARITY, ID]) {
            id
            title {
                english
                romaji
            }
            averageScore
            popularity
            # So we can check if it's a sequel
            relations {
                edges {
                    relationType
                    # TODO: Include startDate to handle dumb shit like 'prequels' that aired later.
                    #node {  # Media
                    #    startDate
                    #}
                }
            }
        }
    }
}'''
    # Because we can't directly exclude sequels from this search, don't cap its return count so we don't miss anything
    # Also search for score - 1, because anilist stores a float on the backend but rounds to int before presenting it,
    # meaning e.g. 79.9% gets excluded even though it shows as 80%. This can give unexpected results so just search
    # 1 under and post-hoc filter out any that didn't round up.
    base_seasons = [show for show in depaginated_request(query=query,
                                                         variables={'score': score - 1, 'popularity': popularity})
                    if show['averageScore'] >= score
                    and not any(relation['relationType'] == 'PREQUEL' for relation in show['relations']['edges'])]

    # Redo the query without the base season restriction, but this time halve the popularity limit and increase the
    # required score by 1, to slightly mitigate sequel bias (sequels are typically half as popular as base seasons,
    # and slightly better-rated). Keep in mind also the above note about score rounding.
    sequels = [show for show in depaginated_request(query=query,
                                                    variables={'score': score, 'popularity': popularity // 2},
                                                    max_count=max_count)
               if show['averageScore'] >= score + 1
               # Ensure base seasons don't get re-counted here
               and any(relation['relationType'] == 'PREQUEL' for relation in show['relations']['edges'])]

    results = sorted(base_seasons + sequels,
                     # Sort on score descending, then popularity ascending
                     key=lambda show: (show['averageScore'], -show['popularity']),
                     reverse=True)
    return results if max_count is None else results[:max_count]


def get_season_hidden_gems(year: int, season: Optional[str] = None,
                           popularity=50_000, percent_nine_plus=0.3, max_count=None) -> list:
    """Given a season or year (e.g. SUMMER 2023), find hidden gems in that season, similarly to get_hidden_gems.

    Since we have a more focused query target, we can afford to use advanced score stats instead of just the meanScore;
    rank on the % of 9+ scores a show has. Add this 'adjustedScore' to the returned show's properties and filter on it
    based on the 'score' arg (default 0.3 = 30%, slightly higher than the global hidden gems search
    function since the adjusted score we use is biased to be higher).
    """
    query = f'''
query ({'$season: MediaSeason, ' if season else ''}$seasonYear: Int, $popularity: Int, $page: Int, $perPage: Int) {{
    Page (page: $page, perPage: $perPage) {{
        pageInfo {{ hasNextPage }}
        media({'season: $season, ' if season else ''}seasonYear: $seasonYear, type: ANIME, format: TV,
              status_not: NOT_YET_RELEASED,
              popularity_lesser: $popularity, sort: [POPULARITY, ID]) {{
            id
            title {{
                english
                romaji
            }}
            status
            nextAiringEpisode {{ episode }}
            popularity
            stats {{
                scoreDistribution {{  # Returns a list of such pairs
                  score
                  amount
                }}
            }}
            # So we can check if it's a sequel
            relations {{ edges {{ relationType }} }}
        }}
    }}
}}'''
    # First query all non-sequels with the full popularity limit and original (adjusted) score requirement.
    base_seasons = [show for show in depaginated_request(query=query,
                                                         variables={'season': season, 'seasonYear': year,
                                                                    'popularity': popularity})
                    if not any(relation['relationType'] == 'PREQUEL' for relation in show['relations']['edges'])]

    # Redo the query without the base season restriction, but this time halve the popularity limit and increase the
    # required score by 1, to slightly mitigate sequel bias (sequels are typically half as popular as base seasons,
    # and slightly better-rated). Keep in mind also the above note about score rounding.
    sequels = [show for show in depaginated_request(query=query,
                                                    variables={'season': season, 'seasonYear': year,
                                                               'popularity': popularity // 2})
               # Ensure base seasons don't get re-counted here
               if any(relation['relationType'] == 'PREQUEL' for relation in show['relations']['edges'])]

    # Measure the % of 9s/10s, ignoring 1s as they are often spam from people who didn't watch a show.
    for show in base_seasons + sequels:
        show['numCountedRatings'] = sum(score['amount'] for score in show['stats']['scoreDistribution']
                                        if score['score'] > 10)
        show['adjustedScore'] = (sum(score['amount'] * score['score'] for score in show['stats']['scoreDistribution']
                                     if score['score'] >= 90)  # Note that anilist uses scores /100 internally
                                 / (100 * show['numCountedRatings']))

    # Filter on adjusted score, increasing the requirement by 5% for sequels.
    # Also skip shows with too few ratings for a meaningful measurement.
    base_seasons = [show for show in base_seasons if show['adjustedScore'] >= percent_nine_plus]
    sequels = [show for show in sequels if show['adjustedScore'] >= percent_nine_plus + 0.05]

    results = sorted(base_seasons + sequels,
                     # Sort on adjusted score descending, then popularity ascending
                     key=lambda show: (show['adjustedScore'], -show['popularity']),
                     reverse=True)

    # Filter out shows that have too few ratings for a reliable measurement, and shows that have only just started
    # airing, as they tend to not have accumulated their actual popularity and/or not have had their score settled yet.
    # We'll go with the 3 ep rule :P
    results = [show for show in results if (show['numCountedRatings'] >= 50
                                            and not (show['status'] == 'RELEASING'
                                                     and show['nextAiringEpisode']['episode'] <= 3))]

    return results if max_count is None else results[:max_count]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Fetch TV anime below a certain popularity and above a certain score (max 100 anime).",
        formatter_class=argparse.RawTextHelpFormatter)  # Preserves newlines in help text
    parser.add_argument('-p', '--popularity', type=int, default=50_000,
                        help="Maximum popularity. Halved for sequels to reduce bias. Default 50,000.")
    parser.add_argument('-s', '--score', type=int, default=None,
                        help="Minimum average score (out of 100). Increased by 1 for sequels to reduce bias.\n"
                             "Default 80.\n"
                             "If a season/year is given, this value is instead the min %% of scores that are 9 or\n"
                             "higher, with slight weight toward 10s. Increased by 5%% for sequels to reduce bias.\n"
                             "Default 30.")
    parser.add_argument('-t', '--top', type=int, default=50, help="Max entries to return. Default 50.")
    parser.add_argument(
        'season', metavar="season/year(s)", type=str, nargs='?', default=None,
        help="If provided, do a more detailed check of the given anime season or year(s).\n"
             'Valid formats: "Summer 2023" (must be quoted), 2023, or 2020-2023. Seasons: Winter/Spring/Summer/Fall.\n'
             "Unlike the coarse global search, fetches score histogram and ranks by %% of scores that are 9 or higher.")
    args = parser.parse_args()

    if not args.season:
        args.score = 80 if args.score is None else args.score  # Split default based on mode
        hidden_gems = get_hidden_gems(popularity=args.popularity, score=args.score, max_count=args.top)

        print("Avg | Users | Name")
        print("------------------")
        for show in hidden_gems:
            title = show['title']['english'] or show['title']['romaji']
            print(f"{show['averageScore']} | {str(show['popularity']).rjust(len(str(args.popularity - 1)))} | {title}")

        print(f"\nCount: {len(hidden_gems)}")
    else:
        # Convert from % to a fraction, and default as needed
        args.score = args.score / 100 if args.score is not None else 0.3

        # Allow XXXX-YYYY year range format.
        if '-' in args.season:
            assert args.season.count('-') == 1, 'Year range format must be "AAAA-BBBB"'
            year1, year2 = [int(year.strip()) for year in args.season.split('-')]
            hidden_gems = []
            for year in range(year1, year2 + 1):
                hidden_gems.extend(get_season_hidden_gems(popularity=args.popularity, percent_nine_plus=args.score,
                                                          max_count=args.top, year=year))

            # Re-sort and cap return count
            hidden_gems.sort(key=lambda show: (show['adjustedScore'], -show['popularity']), reverse=True)
            hidden_gems = hidden_gems if args.top is None else hidden_gems[:args.top]
        else:
            *season, year = args.season.split()
            year = int(year)
            season = season[0].upper() if season else None

            hidden_gems = get_season_hidden_gems(popularity=args.popularity, percent_nine_plus=args.score, max_count=args.top,
                                                 season=season, year=year)

        print("% 9+ | Users | Name")
        print("-------------------------")
        for show in hidden_gems:
            title = show['title']['english'] or show['title']['romaji']
            print(f"{round(100 * show['adjustedScore']):>4} | {str(show['popularity']).rjust(len(str(args.popularity - 1)))} | {title}")

    print(f"\nTotal queries: {safe_post_request.total_queries}")
