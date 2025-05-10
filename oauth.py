import requests
import re
import json
from pathlib import Path

from request_utils import safe_post_request

OAUTH_DIR = Path.home() / ".oauth"
OAUTH_JSON_FILE = OAUTH_DIR / "anilist-tools.json"
AUTH_URL = "https://anilist.co/api/v2/oauth/authorize"
TOKEN_URL = "https://anilist.co/api/v2/oauth/token"
# Not THAT sketchy - Postman callback URL per https://learning.postman.com/docs/sending-requests/authorization/oauth-20/
CALLBACK_URI = "https://oauth.pstmn.io/v1/browser-callback"


# This method is important to prevent any potential mishaps with users authenticating while logged into the wrong
# account (especially if this gets cached permanently incorrectly!).
def access_token_to_username(access_token):
    """Given an AniList access token, verify the username it is associated with."""
    query = '''
query {
  Viewer {
    name
  }
}'''

    return safe_post_request({'query': query}, oauth_token=access_token)['Viewer']['name']


def get_oauth_token(username: str):
    f"""Return an access token for authenticated query requests for the given AniList user.

    If OAuth creds are not saved in ~/.oauth/anilist-tools.json, guides the user through first-time OAuth setup, then
    saves their refresh token into that file so that future calls do not require user interaction.

    OAuth terms TL;DR:
    * Access Token: What actually gets put in other API requests to auth them. This function returns an access token.
    * OAuth Client: Tells AniList what tool the tokens are for. Only one is needed, and it can be used across 
                    different users. We don't distribute one with this script because that is Bad Security.
    * Authorization Code: An intermediate value that lets us request a refresh token (and access token).
    #                     OAuth doesn't give us those tokens directly for Security Reasons.
    * Refresh token: Normally, this is a token that lets you get more access tokens. However, AniList doesn't support
                     exchanging refresh tokens, instead just making its access tokens very long-lived.
    """
    oauth_config = {}
    OAUTH_DIR.mkdir(exist_ok=True)
    if OAUTH_JSON_FILE.exists():
        with open(OAUTH_JSON_FILE, 'r') as f:
            oauth_config = json.loads(f.read())

    # Verify we have a stored OAuth client and prompt the user to create one if not
    if 'client_id' not in oauth_config or 'client_secret' not in oauth_config:
        print("[One-time setup] Anilist OAuth client required. Please follow:\n"
              "https://anilist.gitbook.io/anilist-apiv2-docs/overview/oauth/getting-started#using-oauth\n"
              "to create one. Use the following values:\n"
              "    Name: anilist-tools (or whatever you want, doesn't matter)\n"
              f"    Redirect URL: {CALLBACK_URI}\n"
              "Then provide the client ID and secret here:\n")
        client_id_str = input("Client ID: ").strip()
        if not client_id_str.isdigit():
            raise ValueError("Invalid client ID; should be a number, without quotes.")
        oauth_config['client_id'] = int(client_id_str)

        oauth_config['client_secret'] = input("Client Secret: ").strip()
        if not oauth_config['client_secret'].isalnum():
            raise ValueError("Invalid client secret; should be alphanumeric, without quotes.")

        # Save the client info immediately so we don't make the user do this twice if any below step fails.
        with open(OAUTH_JSON_FILE, 'w') as f:
            f.write(json.dumps(oauth_config))

    if 'users' not in oauth_config:
        oauth_config['users'] = {}

    # If we already have an access token stored, do a paranoid check that it matches the user we asked for, or else
    # VERY bad things could happen, then return it.
    # We also conveniently use this to check if the stored token is expired or invalidated for any other reason, and
    # delete it if it was.
    if username in oauth_config['users'] and 'access_token' in oauth_config['users'][username]:
        try:
            if access_token_to_username(oauth_config['users'][username]['access_token']).lower() != username.lower():
                raise RuntimeError("Stored OAuth login does not match provided username.")

            return oauth_config['users'][username]['access_token']
        except Exception as e:  # This redundantly catches the above exception but rearranging is uglier.
            if "Invalid token" in str(e):
                print("Your Anilist OAuth token has expired, starting OAuth flow.\n")
                del oauth_config['users'][username]['access_token']
            else:
                raise

    # If we don't have a refresh token stored for this user or it was invalidated, guide them through the OAuth flow to
    # get one. Refresh tokens allow us to get access tokens without future user prompts.

    # First send user through OAuth flow to get an authorization code.
    # We don't open the browser/URL for them in case they want to log in to an alt in incognito or something.
    oauth_redirect_url = f"{AUTH_URL}?response_type=code&client_id={oauth_config['client_id']}&redirect_uri={CALLBACK_URI}"
    print("OAuth grant required. In a browser:\n\n"
          f"1. Login to `{username}` in AniList.\n"
          f"2. Visit the following URL to grant access:\n{oauth_redirect_url}\n"
          "3. You will be redirected. Paste the full final redirected URL below.\n")
    redirected_url = input("Final URL: ")
    auth_code = re.search("code=([^&]*)", redirected_url).group(1)

    # Exchange the obtained auth code for an access token. Anilist also returns a refresh token but doesn't support
    # using it and just gives us a year-long access token instead.
    resp = requests.post(TOKEN_URL,
                         data={'grant_type': 'authorization_code', 'code': auth_code, 'redirect_uri': CALLBACK_URI},
                         verify=False, allow_redirects=False,
                         auth=(oauth_config['client_id'], oauth_config['client_secret']))
    if resp.status_code != 200:
        raise Exception(f"AniList OAuth API gave {resp.status_code} response on auth code exchange with error: {resp.text}")

    resp_json = json.loads(resp.text)

    if 'access_token' not in resp_json:
        raise Exception('Access token missing from AniList OAuth response.')

    # Before saving the access token, make sure that the given access token actually matches the user we asked for (to
    # within lazy user-typing constraints; usernames are case-unique anyway).
    if access_token_to_username(resp_json['access_token']).lower() != username.lower():
        raise RuntimeError("Anilist API returned OAuth token not matching given username. WTF?")

    if username not in oauth_config['users']:
        oauth_config['users'][username] = {}
    oauth_config['users'][username]['access_token'] = resp_json['access_token']

    with open(OAUTH_JSON_FILE, 'w') as f:
        f.write(json.dumps(oauth_config))

    return resp_json['access_token']
