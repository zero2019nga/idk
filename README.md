# limits free bot — x.2re single-file fix

This build fixes:
`ModuleNotFoundError: No module named 'x2re_engine'`

Everything is inside `main.py`, so Railway cannot miss the `x2re_engine` folder.

## Files

main.py
requirements.txt
Dockerfile
Procfile
railway.json
x2re_layer_bank.bin

## Railway variables

BOT_TOKEN=your Discord bot token
ALLOWED_CHANNEL_ID=your predict channel ID
ANNOUNCEMENT_CHANNEL_ID=your announcement channel ID
OWNER_ID=your Discord user ID

Optional:
MAX_MINES=5
MAX_SAFE_SPOTS=7
HISTORY_COUNT=500

## Important

Extract the ZIP and upload the files inside. Do not upload the ZIP itself.
