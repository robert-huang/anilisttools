"""Fetch anime below a certain popularity and above a certain score."""

import argparse

from request_utils import safe_post_request, depaginated_request


# TODO: Allow passing a user, and use their personal scores instead of average score (to get shows *they* would consider
#       hidden gems).
# Other unmitigated sources of bias: anime age - longer time to gain popularity and increasing number of users per year.
def get_hidden_gems(popularity=50_000, score=80, max_count=None) -> list:
    """Given popularity and score cutoffs, return all anime that are below the given popularity and
    above the given (average) score. Default <= 50,000 popularity and >= 80 score.

    Pass max_count to limit results length.
    """
    # First, query the full popularity limit with only base seasons included
    query = '''
query ($score: Int, $popularity: Int, $page: Int, $perPage: Int) {
    Page (page: $page, perPage: $perPage) {
        pageInfo {
            hasNextPage
        }
        # IMPORTANT: Always include ID in the sort, as the anilist API is bugged - if ties are possible,
        #            pagination can omit some results while duplicating others at the page borders.
        media(type: ANIME, format:TV, averageScore_greater:$score, popularity_lesser:$popularity, 
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
    base_ids = set(show['id'] for show in base_seasons)

    # Redo the query without the base season restriction, but this time halve the popularity limit and increase the
    # required score by 1, to slightly mitigate sequel bias (sequels are typically half as popular as base seasons,
    # and slightly better-rated). Keep in mind also the above note about score rounding.
    sequel_adjusted = [show for show in depaginated_request(query=query,
                                                            variables={'score': score, 'popularity': popularity // 2},
                                                            max_count=max_count)
                       if show['averageScore'] >= score + 1
                       and show['id'] not in base_ids]  # Avoid duplicates if any base season met the stricter limit

    results = sorted(base_seasons + sequel_adjusted,
                     # Sort on score descending, then popularity ascending
                     key=lambda show: (show['averageScore'], -show['popularity']),
                     reverse=True)
    return results if max_count is None else results[:max_count]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Fetch TV anime below a certain popularity and above a certain score (max 100 anime).",
        formatter_class=argparse.RawTextHelpFormatter)  # Preserves newlines in help text
    parser.add_argument('-p', '--popularity', type=int, default=50_000,
                        help="Maximum popularity. Halved for sequels to mitigate bias. Default 50,000.")
    parser.add_argument('-s', '--score', type=int, default=80,
                        help="Minimum average score (out of 100). Increased by 1 for sequels to mitigate bias."
                             "\nDefault 80.")
    parser.add_argument('-t', '--top', type=int, default=50, help="Max entries to return. Default 50.")
    args = parser.parse_args()

    print("Avg | Users | Name")
    print("------------------")
    hidden_gems = get_hidden_gems(popularity=args.popularity, score=args.score, max_count=args.top)
    for show in hidden_gems:
        title = show['title']['english'] or show['title']['romaji']
        print(f"{show['averageScore']} | {str(show['popularity']).rjust(5)} | {title}")

    print(f"\nCount: {len(hidden_gems)}")

    print(f"\nTotal queries: {safe_post_request.total_queries}")
