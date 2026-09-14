import os
import requests
import dotenv

dotenv.load_dotenv()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")


def send_slack_message(text: str) -> bool:
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL is not set, skipping Slack message.")
        return False
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json={"text": text}, timeout=10)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Failed to send Slack message: {e}")
        return False