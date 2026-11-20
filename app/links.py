"""Project links shown in Settings > About. Edit these four values."""
GITHUB_URL = "https://github.com/YOUR_USERNAME/DNSChanger"
DONATE_URL = "https://example.com/donate"
TELEGRAM_ID = "@YOUR_TELEGRAM_ID"          # personal / support account
CHANNEL_ID = "@YOUR_CHANNEL_ID"            # project channel


def telegram_url(handle: str) -> str:
    return "https://t.me/" + handle.strip().lstrip("@")
