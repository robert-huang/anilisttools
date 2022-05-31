import requests
import re
import json
import webbrowser
import time

def get_oauth_token(client_id, client_secret):
    """Retrieves an access token for athenticated query requests.

    Requires user input in one of the steps, unavoidable due to OAuth limitations.
    https://community.auth0.com/t/how-to-do-authorisation-code-flow-programmatically/61497/4
    """
    authorize_url = "https://anilist.co/api/v2/oauth/authorize"
    token_url = "https://anilist.co/api/v2/oauth/token"
    callback_uri = "https://oauth.pstmn.io/v1/browser-callback"

    authorization_redirect_url = authorize_url + \
        "?response_type=code&client_id=" + str(client_id) + "&redirect_uri=" + callback_uri
    print("the browser will now open, paste the full redirected url here: ")
    time.sleep(3)
    webbrowser.open(authorization_redirect_url)
    redirected_url = input("url: ")
    authorization_code = re.search("code=(.*)", redirected_url).group(1)

    data = {"grant_type": "authorization_code",
            "code": authorization_code, "redirect_uri": callback_uri}
    resp = requests.post(
        token_url, data=data, verify=False, allow_redirects=False, auth=(client_id, client_secret))

    if resp.status_code == 200:
        return json.loads(resp.text)['access_token']
    else:
        raise Exception(
            f"AniList API gave {resp.status_code} response with error: {resp.text}")
