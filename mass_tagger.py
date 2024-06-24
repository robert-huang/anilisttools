from request_utils import safe_post_request, depaginated_request
from amq_list_syncer import ask_for_confirm_or_skip
import oauth
import json
import argparse
from datetime import datetime
import re

MEDIA_TYPE = ['ANIME', 'MANGA']

REPLACE_LISTS = []

REPLACE_DICT = {
    # '': 'add to all shows with no notes',
    '#watched_airing': '#airing'
    # 'updated': 'updated via mass tagger'
}

list_query = '''
query ($userName: String, $mediaType: MediaType) {
  MediaListCollection(userName: $userName, type: $mediaType, sort:[SCORE_DESC, FINISHED_ON_DESC], forceSingleCompletedList: true) {
  	lists {
  	  name
  	  status
      entries {
        media {
            id
            title {
                romaji
            }
        }
        score (format: POINT_100)
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
        notes
      }
  	}
  }
}'''

update_notes_query = '''
mutation($mediaId:Int,$notes:String){
    SaveMediaListEntry(mediaId:$mediaId,notes:$notes){
        notes
    }
}'''

def ask_for_confirm_or_skip(confirmation_question: str):
    if args.force:
        return True

    confirm = input(f"{confirmation_question}? (y/n/skip): ").strip().lower()
    if confirm == 'skip':
        return False
    elif not confirm.startswith('y'):
        raise Exception("User cancelled operation.")

    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--username')
    parser.add_argument('--force', action='store_true', help="Do not ask for confirmation on updating entry notes.")
    args = parser.parse_args()

    oauth_token = oauth.get_oauth_token(args.username)

    output = []

    for type in MEDIA_TYPE:
        media_json = safe_post_request({'query': list_query, 'variables': {'userName': args.username, 'mediaType': type}}, oauth_token=oauth_token)
        entry_lists = media_json['MediaListCollection']['lists']
        for list in entry_lists:
            print(f'Processing {list["name"]} {type} list...')
            if len(REPLACE_LISTS) == 0 or \
                (len(REPLACE_LISTS) > 0 and list['name'] in REPLACE_LISTS):
                for entry in list['entries']:
                    notes = entry['notes']
                    new_notes = None
                    replace = False
                    if notes:
                        for src, tar in REPLACE_DICT.items():
                            if src == '':
                                continue
                            if notes.find(src) != -1:
                                new_notes = notes.replace(src, tar, 1)
                                replace = True
                    elif blank_notes := REPLACE_DICT.get(''):
                        new_notes = blank_notes
                        replace = True

                    if replace and ask_for_confirm_or_skip(f'Update notes for {entry["media"]["title"]["romaji"]}'):
                            variables = {'mediaId': entry['media']['id'], 'notes': new_notes}
                            safe_post_request({'query': update_notes_query, 'variables': variables}, oauth_token=oauth_token)
