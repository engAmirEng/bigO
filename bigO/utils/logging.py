import logging
from datetime import datetime

import requests
from requests.auth import HTTPBasicAuth


class BasicLokiHandler(logging.Handler):
    """
    This is a super basic setup to send logs to Loki
    """

    def __init__(self, url, labels: dict, username: str, password: str):
        super().__init__()
        self.url = url
        self.labels = labels or {}
        self.basic_auth = HTTPBasicAuth(username, password)

    def emit(self, record):
        # Format the log entry as a Loki-compatible payload
        log_entry = self.format(record)
        timestamp = int(datetime.utcnow().timestamp() * 1e9)  # Nanoseconds
        payload = {"streams": [{"stream": {**self.labels, "level": record.levelname}, "values": [[str(timestamp), log_entry]]}]}
        headers = {"Content-Type": "application/json"}

        try:
            # Send log entry to Loki
            res = requests.post(self.url, headers=headers, json=payload, auth=self.basic_auth)
            print(res)
        except requests.RequestException as e:
            # Handle logging errors (optional)
            print(f"Error sending log to Loki: {e}")
