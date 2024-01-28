import logging
import os
import time

from dotenv import load_dotenv
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from importers.credit_card_import import CreditCardImporter

load_dotenv()
CC_IMPORTS_DIR = os.getenv("CC_IMPORTS_DIR")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MyHandler(FileSystemEventHandler):
    def on_created(self, event):
        # Only act on .csv files
        print(event)
        if (
            event.src_path.endswith(".csv.tmp")
            and event.src_path != "CreditCardImporter.csv"
        ):
            path = event.src_path.strip(".tmp")
            path = path.replace(".syncthing.", "")
            time.sleep(3)
            my_trigger(path)


def my_trigger(file_path):
    logging.info("A new .csv file has been created!")
    CreditCardImporter(CC_IMPORTS_DIR).run(file_path)
    logging.info("Credit card job complete.")


def monitor_directory(path):
    event_handler = MyHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    logging.info(f"Watching dir: {path}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    monitor_directory(CC_IMPORTS_DIR)
