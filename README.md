# dexcom_to_elasticsearch
(Very) simple app that allows a user to o-auth with a Dexcom develepor app,
import glucose values from a CGM, and send that data to Elasticsearch

## Usage

### Requirements

Requires Python 3.7.

```
pip install -r requirements.txt
```

### Config

Go to https://developer.dexcom.com/ and make an account and an app. Copy
`dexcom/settings.py.sample` to `dexcom/settings.py` and fill in the details
for your dexcom application, including client_id, client_secret, and
redirect_uri. You'll also need auth information for your elasticsearch cluster.

### Running the app

```
python3 run.py
```

The first time the app runs it will walk you through the oauth process for your
dexcom account. Once authorized, the app will start at the beginning of your
available data from dexcom, and walk through an hour at a time, indexing all
glucose readings into elasticsearch. It stores its progress in a `cursor` file
so that it can start where it left off next time it runs.

The app will handle refreshing your tokens, and whenever it runs out of data it
will sleep for 5 minutes before checking again.

Note that the Dexcom G6 app only uploads once per hour, with a 3 hour lag, so
data will typicall be 3-4 hours stale.

## Troubleshooting

If something goes wrong, delete `tokens` so you can re-authorize. You can also
edit `cursor` with a custom start point for indexing your data if you're missing
data or want to restart from the beginning.