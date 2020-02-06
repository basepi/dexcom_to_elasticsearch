"""
Simple connector between Dexcom's developer API and elasticsearch
"""
import json
import logging
import os
import time
from datetime import datetime, timedelta

import elasticsearch
import elasticsearch.helpers
import requests

import dexcom.settings as settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
timestr = "%Y-%m-%dT%H:%M:%S"
time_window = timedelta(hours=1)


def run():
    """
    Main entrypoint for the application
    """
    access_token = None
    refresh_token = None
    expires = 0
    tokens_file = settings.tokens_file
    cursor_file = settings.cursor_file
    base_url = settings.base_url
    cursor = datetime.fromtimestamp(0)
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

    # Set up elasticsearch
    es_endpoints = settings.es_endpoints
    es_user = settings.es_user
    es_password = settings.es_password
    es_index = settings.es_index
    es = elasticsearch.Elasticsearch(es_endpoints, http_auth=(es_user, es_password), scheme="https", port=443)

    # Check for previous cursor
    earliest_egv = None
    latest_egv = None
    if os.path.isfile(cursor_file):
        try:
            with open(cursor_file, "r") as f:
                cursor = datetime.strptime(f.read().strip(), timestr)
        except:
            pass

    while True:
        # Check if we need a new token
        if time.time() > expires:
            access_token, refresh_token, expires = auth(refresh=refresh_token)

        if not earliest_egv or cursor > latest_egv:
            # Get dataranges for the user
            try:
                headers = {"authorization": f"Bearer {access_token}"}
                r = requests.get(base_url + "/v2/users/self/dataRange", headers=headers)
                r.raise_for_status()
                data = r.json()
            except ConnectionError as e:
                log.error(f"Received a connection error from datarange endpoint: {e}")
                time.sleep(5)
                continue

            # Sometimes egv can have a decimal on the seconds. Throw it away.
            earliest_egv = datetime.strptime(data["egvs"]["start"]["systemTime"].split(".", 1)[0], timestr)
            latest_egv = datetime.strptime(data["egvs"]["end"]["systemTime"].split(".", 1)[0], timestr)

        if earliest_egv > cursor:
            cursor = earliest_egv
        elif cursor > latest_egv:
            # We've fetched all the records, sleep for 5 minutes
            log.info("No new records found. Sleeping for 5 minutes.")
            time.sleep(300)
            continue

        # Fetch an hour of estimated glucose values (egv)
        finish = cursor + time_window

        startstr = cursor.strftime(timestr)
        finishstr = finish.strftime(timestr)

        try:
            headers = {"authorization": f"Bearer {access_token}"}
            r = requests.get(
                base_url + f"/v2/users/self/egvs?startDate={startstr}&endDate={finishstr}", headers=headers
            )
            r.raise_for_status()
            data = r.json()
        except ConnectionError as e:
            log.error(f"Received a ConnectionResetError querying egvs: {e}")
            time.sleep(5)
            continue

        data = format_data(data, es_index) if data else {}

        if data:
            # Bulk send to elasticsearch
            elasticsearch.helpers.bulk(es, data)
            log.info(f"Indexed {len(data)} records from {startstr} to {finishstr}")

            # Record the time of the newest EGV we have (they are sorted from newest to oldest)
            last_egv = datetime.strptime(data[0]["_source"]["@timestamp"], timestr)
            # Update the cursor to one second past our last indexed event
            cursor = last_egv + timedelta(seconds=1)

        # We can skip ahead if the window was empty but there are already more
        # events post-window
        if finish < latest_egv:
            if not data:
                # No events in this window (and more events after this window),
                # likely due to sensor change.
                log.info(
                    "No events in the time window, but more events after. "
                    "This is likely due to a sensor change or malfunction. "
                    "Skipping time window."
                )
            cursor = finish

        # Store the cursor in case we get interrupted
        with open(cursor_file, "w") as f:
            f.write(cursor.strftime(timestr))

        time.sleep(0.1)


def format_data(data, es_index):
    """
    Format data for bulk indexing into elasticsearch
    """
    unit = data["unit"]
    rate_unit = data["rateUnit"]
    egvs = data["egvs"]
    docs = []

    for record in egvs:
        record["unit"] = unit
        record["rate_unit"] = rate_unit
        record["@timestamp"] = record.pop("systemTime")
        record.pop("displayTime")
        record["realtime_value"] = record.pop("realtimeValue")
        record["smoothed_value"] = record.pop("smoothedValue")
        record["trend_rate"] = record.pop("trendRate")
        docs.append({"_index": es_index, "_type": "document", "_source": record})

    return docs


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
            "After logging in, you will be redirected. Please "
            "paste the URL of that redirect into the terminal. Note that the "
            f"url will expire after one minute.\n\n{auth_url}\n\nPaste here: "
        )
        auth_code = response.strip().partition("code=")[2]

        params = {
            "client_secret": client_secret,
            "client_id": client_id,
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        headers = {"content-type": "application/x-www-form-urlencoded", "cache-control": "no-cache"}
        r = requests.post(base_url + "/v2/oauth2/token", data=params, headers=headers)
        r.raise_for_status()
        data = r.json()
    else:
        log.info("Refreshing token.")
        params = {
            "client_secret": client_secret,
            "client_id": client_id,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
            "redirect_uri": redirect_uri,
        }
        headers = {"content-type": "application/x-www-form-urlencoded", "cache-control": "no-cache"}
        r = requests.post(base_url + "/v2/oauth2/token", data=params, headers=headers)
        r.raise_for_status()
        data = r.json()

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
