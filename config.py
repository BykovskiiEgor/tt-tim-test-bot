import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
FILES_ROOT = os.getenv("FILES_ROOT", "./files")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))  