"""
Simple connector between Dexcom's developer API and elasticsearch
"""
import json
import logging
import os

import dexcom.settings as settings

log = logging.getLogger(__name__)


def run():
    """
    Main entrypoint for the application
    """
    access_token = None
    refresh_token = None
    tokens_file = settings.tokens_file
    if os.path.isfile(tokens_file):
        try:
            with open(tokens_file, "r") as f:
                tokens = json.load(f)
            access_token = tokens["access_token"]
            refresh_token = tokens["refresh_token"]
        except:
            pass

    if not access_token or not refresh_token:
        access_token, refresh_token = auth()

    try:
        with open(tokens_file, "w") as f:
            json.dump({"access_token": access_token, "refresh_token": refresh_token})
    except:
        log.exception(f"Unable to dump tokens to token_file {tokens_file}")


def auth():
    """
    Authentication with Dexcom's o-auth system
    """
    pass


if __name__ == "__main__":
    run()
