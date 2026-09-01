import os
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set in .env file!")

# Administrator Telegram ID
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0

# Database Path
DB_PATH = os.path.join(os.path.dirname(__file__), "database", "taxi.db")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Proxy settings
USE_PROXY = os.getenv("USE_PROXY", "False").lower() == "true"
PROXY_URL = os.getenv("PROXY_URL", "")

# Payment Provider Token (Click/Payme)
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
