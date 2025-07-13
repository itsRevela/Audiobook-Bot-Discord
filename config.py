# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
AUDIOBOOK_PATH = "audiobooks"
BOOKS_PER_PAGE = 20