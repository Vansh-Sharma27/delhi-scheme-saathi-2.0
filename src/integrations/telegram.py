"""Temporary Telegram adapter exports during Phase 6 caller migration."""

import sys

from src.dss.infrastructure import telegram
from src.dss.infrastructure.telegram import DEFAULT_BOT_COMMANDS as DEFAULT_BOT_COMMANDS
from src.dss.infrastructure.telegram import TelegramClient as TelegramClient
from src.dss.infrastructure.telegram import get_telegram_client as get_telegram_client

sys.modules[__name__] = telegram
