"""
Minimal Flask health-check endpoint so Render sees an open port (required
for Render "Web Service" deployments) and UptimeRobot has something to ping
to keep the service from idling/sleeping on free tiers.

This carries no odds data â€” it's purely "is the process alive". Runs in a
background thread since the real work (the async poll loop in main.py) uses
asyncio on the main thread.
"""

import logging

from flask import Flask

logger = logging.getLogger("arb_alert.health")

app = Flask(__name__)


@app.route("/", methods=["GET", "HEAD", "POST"])
def health():
    return "Naija arb alert engine is running.", 200


def start_health_server(port: int) -> None:
    logger.info("Health check server listening on port %d", port)
    # use_reloader=False is required â€” Flask's reloader tries to spawn a
    # second process, which breaks running this inside a background thread.
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
