"""
Simple connector between Dexcom's developer API and elasticsearch
"""
import http.client
import json
import logging
import os
import time

import dexcom.settings as settings

log = logging.getLogger(__name__)


def run():
    """
    Main entrypoint for the application
    """
    access_token = None
    refresh_token = None
    expires = 0
    tokens_file = settings.tokens_file
    if os.path.isfile(tokens_file):
        try:
            with open(tokens_file, "r") as f:
                tokens = json.load(f)
            access_token = tokens["access_token"]
            refresh_token = tokens["refresh_token"]
            expires = tokens["expires"]
        except:
            pass

    if not access_token or not refresh_token:
        access_token, refresh_token, expires = auth()

    while True:
        if time.time() > expires:
            access_token, refresh_token, expires = auth(refresh=refresh_token)

        time.sleep(10)

    print(f"We have tokens!")


def auth(refresh=False):
    """
    Authentication with Dexcom's o-auth system

    If refresh is not False, it should be a refresh token used to refresh the
    access token.
    """
    client_id = settings.client_id
    client_secret = settings.client_secret
    base_url = settings.base_url
    redirect_uri = settings.redirect_uri
    tokens_file = settings.tokens_file

    data = {}
    if refresh is False:
        auth_url = f"{base_url}/v2/oauth2/login?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=offline_access"  # noqa: E501

        response = input(
            "Please go to the following URL, and log into your Dexcom account. "
            "After logging in, you will be redirected to an error page. Please "
            "paste the URL of that error page into the terminal. Note that the "
            f"url will expire after one minute.\n\n{auth_url}\n\nPaste here: "
        )
        auth_code = response.strip().partition("code=")[2]

        conn = http.client.HTTPSConnection("api.dexcom.com")
        payload = f"client_secret={client_secret}&client_id={client_id}&code={auth_code}&grant_type=authorization_code&redirect_uri={redirect_uri}"  # noqa: E501
        headers = {"content-type": "application/x-www-form-urlencoded", "cache-control": "no-cache"}
        conn.request("POST", "/v2/oauth2/token", payload, headers)
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        conn.close()
    else:
        log.info("Refreshing token.")
        conn = http.client.HTTPSConnection("api.dexcom.com")
        payload = f"client_secret={client_secret}&client_id={client_id}&refresh_token={refresh}&grant_type=refresh_token&redirect_uri={redirect_uri}"  # noqa: E501
        headers = {"content-type": "application/x-www-form-urlencoded", "cache-control": "no-cache"}
        conn.request("POST", "/v2/oauth2/token", payload, headers)
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        conn.close()

    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    expires = time.time() + data["expires_in"] - 10  # 10 second grace period

    try:
        with open(tokens_file, "w") as f:
            json.dump({"access_token": access_token, "refresh_token": refresh_token, "expires": expires}, f)
        log.info("Token fetch and save successful.")
    except:
        log.exception(f"Unable to dump tokens to token_file {tokens_file}")

    return (access_token, refresh_token, expires)


if __name__ == "__main__":
    run()
