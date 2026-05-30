# Discord adapter (stub)

Not implemented. Documented here as a reference for the adapter shape.

## Required env vars

```bash
DISCORD_BOT_TOKEN=     # bot token from https://discord.com/developers/applications
DISCORD_CHANNEL_ID=    # restrict the bot to one channel
```

## Sketch

```python
# integrations/discord/app.py
import discord
from . import client
from .config import token, channel_id

bot = discord.Bot()

@bot.event
async def on_message(message):
    if message.channel.id != channel_id:
        return
    if message.content.startswith("!status"):
        await message.channel.send(client.format_status())

bot.run(token)
```

`client.format_status()` calls `subprocess.run(["python3",
"scripts/memory.py", "current", "--id-only"])` and friends — the same
shape `integrations/slack/client.py` uses. Copy that file and retarget
the medium-specific bits.
