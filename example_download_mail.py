from jbmailbot.config import AppConfig
from jbmailbot.mailfetch import make_async_mail_fetcher
from jbmailbot.storage import MemoryMailStorage

if __name__ == "__main__":
    config = AppConfig()  # pyright: ignore
    storage = MemoryMailStorage()
    downloader = make_async_mail_fetcher(config.mailbots[0].imap, storage)
    downloader.fetch_and_save_messages()
    for message in storage.get_unreplied():
        print(message)
