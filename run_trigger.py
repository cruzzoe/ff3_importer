import logging
import os
import time

from dotenv import load_dotenv
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from importers.credit_card_import import CreditCardImporter

load_dotenv()
CC_IMPORTS_DIR=os.getenv("CC_IMPORTS_DIR")

class MyHandler(FileSystemEventHandler):
    def on_created(self, event):
        # Only act on .csv files
        if event.src_path.endswith('.csv'):
            my_trigger(event.src_path)

def my_trigger(file_path):
    logging.info("A new .csv file has been created!")
    CreditCardImporter(CC_IMPORTS_DIR).run(file_path)
    logging.info('Credit card job complete.')

def monitor_directory(path):
    event_handler = MyHandler()
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    monitor_directory(CC_IMPORTS_DIR)