import json
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
        payload = {
            "streams": [
                {"stream": {**self.labels, "level": record.levelname}, "values": [[str(timestamp), log_entry]]}
            ]
        }
        headers = {"Content-Type": "application/json"}

        try:
            # Send log entry to Loki
            res = requests.post(self.url, headers=headers, json=payload, auth=self.basic_auth)
            print(res)
        except requests.RequestException as e:
            # Handle logging errors (optional)
            print(f"Error sending log to Loki: {e}")


def split_by_total_length(strings, max_length):
    result = []
    current_group = []
    current_length = 0

    for s in strings:
        len_s = len(json.dumps(s))
        # If a single string exceeds the max_length, place it in its own group
        if len_s > max_length:
            # If there's any current group, append it to the result before starting a new group
            if current_group:
                result.append(current_group)
                current_group = []
                current_length = 0
            # Add the large string as its own group
            result.append([s])
        elif current_length + len_s > max_length:
            # If adding the string exceeds max_length, finalize the current group and start a new one
            result.append(current_group)
            current_group = [s]
            current_length = len_s
        else:
            # Otherwise, add the string to the current group
            current_group.append(s)
            current_length += len_s

    # Add the last group if it's not empty
    if current_group:
        result.append(current_group)

    return result
