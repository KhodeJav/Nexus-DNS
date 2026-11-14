"""Project links shown in Settings > About. Edit these four values."""
GITHUB_URL = "https://github.com/KhodeJav/Nexus-DNS"
DONATE_URL = "https://payments.tipora.ir"
TELEGRAM_ID = "@KhodeJaw"          # personal / support account
CHANNEL_ID = "@NexusDNS"            # project channel


def telegram_url(handle: str) -> str:
    return "https://t.me/" + handle.strip().lstrip("@")
