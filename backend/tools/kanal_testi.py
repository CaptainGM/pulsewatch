import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.notifier import send_test_channel

CHANNELS = {
    "slack": {"webhook_url": os.getenv("SLACK_WEBHOOK_URL", "")},
    "discord": {"webhook_url": os.getenv("DISCORD_WEBHOOK_URL", "")},
    "telegram": {
        "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
    },
}


async def main():
    for kind, config in CHANNELS.items():
        if not all(config.values()):
            print(f"{kind}: atlandi (ortam degiskenleri tanimli degil)")
            continue
        channel = SimpleNamespace(kind=kind, config=config)
        success, error = await send_test_channel(channel)
        print(f"{kind}: {'basarili' if success else 'hata: ' + str(error)}")


if __name__ == "__main__":
    asyncio.run(main())
