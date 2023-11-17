import datetime
import os
import subprocess
import time
import calendar
import logging

# from bs4 import BeautifulSoup
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from logging.handlers import RotatingFileHandler

import pandas as pd

load_dotenv()

TOKEN = os.getenv("TOKEN")
HOME_IP = os.getenv("HOME_IP")
USER=os.getenv("BANK_ACCOUNT_USER")
PASSWORD=os.getenv("BANK_ACCOUNT_PASSWORD")
DOWNLOAD_DIR=os.getenv("DOWNLOAD_DIR")

# log_file = '' os.getenv("LOG_LOCATION")

# handler = RotatingFileHandler(
#     log_file,
#     maxBytes=1024 * 1024,
#     backupCount=5,
# )
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S %Z",
)
# handler.setFormatter(formatter)

# Create a StreamHandler to log messages to the terminal
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S %Z"
    )
)

logger = logging.getLogger(__name__)
logger.addHandler(stream_handler)
# logger.addHandler(handler)

# should_roll_over = os.path.isfile(log_file)
# if should_roll_over:  # log already exists, roll over!
#     handler.doRollover()

logger.setLevel(logging.INFO)




def notify(header, message):
    """Send notification to gotify"""
    cmd = f'curl "http://{HOME_IP}:8991/message?token={TOKEN}" -F "title=[{header}]" -F "message"="{message}" -F "priority=5"'
    subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )


def get_file_path(download_dir):
    """From the download directory get the file path of the downloaded file based on selecting the most recently saved file."""
    files = os.listdir(download_dir)
    files.sort(key=lambda x: os.path.getmtime(os.path.join(download_dir, x)))
    file_path = os.path.join(download_dir, files[-1])
    return file_path


def download_bank_csv(month_start, month_end, download_dir):
    """Use selenium to download csv file from bank acount"""
    # change month_start to str format "2023/10/01"
    month_start = month_start.strftime("%Y/%m/%d")
    month_end = month_end.strftime("%Y/%m/%d")

    chrome_options = Options()
    chrome_options.add_experimental_option(
    # On Mac - Chrome prompts to download the file if default directory is changed.
    # I dont think this happens on ubuntu
        "prefs",
        {
            # "download.default_directory": download_dir,
            # "safebrowsing.enabled": True,
            # "download.prompt_for_download": False,
            # "safebrowsing_for_trusted_sources_enabled": False
        },
    )
    # TODO enable this to make headless
    # chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(options=chrome_options)

    driver.get(
        "https://login.smbctb.co.jp/ib/portal/POSNIN1prestiatop.prst?LOCALE=en_JP"
    )
    driver.implicitly_wait(0.5)

    time.sleep(1)
    driver.find_element(By.ID, "dispuserId").send_keys(USER)
    driver.find_element(By.ID, "disppassword").send_keys(PASSWORD)
    # Find the submit button and click it
    submit_button = driver.find_element(By.CSS_SELECTOR, "a.btn.btn-large.btn-inverse")
    submit_button.click()
    time.sleep(1)

    link = driver.find_elements(By.CSS_SELECTOR, "a.link-arrow")[3]
    link.click()
    time.sleep(1)
    # fill in the form
    from_field = driver.find_element(By.NAME, "tradingHistoryPeriodFrom")
    up_to_field = driver.find_element(By.NAME, "tradingHistoryPeriodTo")

    from_field.clear()
    from_field.send_keys(month_start)
    up_to_field.clear()
    up_to_field.send_keys(month_end)
    time.sleep(1)
    submit_button = driver.find_element(By.CSS_SELECTOR, "a.btn.btn-small.btn-download")
    submit_button.click()
    time.sleep(6)
    driver.quit()


# def upload_to_firefly(input_path):
#     # run in a subprocess
#     logger.info("Uploading file to firefly...")
#     cmd = (
#         f"docker exec -it [container-id] php artisan importer:import bank_import_format.json {input_path}}"
#     )

#     cmd = 'docker run \
#         --rm \
#         -v $PWD:/import \
#         -e FIREFLY_III_ACCESS_TOKEN= \
#         -e IMPORT_DIR_ALLOWLIST=/import \
#         -e FIREFLY_III_URL= \
#         -e WEB_SERVER=false \
#         fireflyiii/data-importer:latest'
    
#     subprocess.run(
#         cmd,
#         shell=True,
#         stdout=subprocess.PIPE,
#         stderr=subprocess.PIPE,
#         text=True,
#         check=True,
#     )
#     logger.info("File uploaded to firefly")


def transform_data(file_path, month):
    """Read csv file path with pandas and change encoding from shift-jis to utf-8.
    Then save file to csv."""
    logger.info(f"Beginning Transform...")
    column_names = ["Date", "Destination", "Amount", "Ignore"]
    df = pd.read_csv(file_path, encoding="shift_jis", header=None, names=column_names)
    file_path = file_path.split(".")[0]
    target = f"Bank_transactions_{month}" + "_processed.csv"
    df.to_csv(target, encoding="utf-8")
    logger.info(f"File saved down to target: {target}")


if __name__ == "__main__":
    current_month = datetime.datetime.today()
    previous_month = current_month - datetime.timedelta(days=30)
    _, last_day = calendar.monthrange(previous_month.year, previous_month.month)

    month_str = previous_month.strftime("%B")
    logger.info(previous_month)
    month_start = datetime.datetime(previous_month.year, previous_month.month, 1)
    month_end = datetime.datetime(previous_month.year, previous_month.month, last_day)
    logger.info(month_start)
    logger.info(month_end)
    download_dir = DOWNLOAD_DIR
    download_bank_csv(month_start, month_end, download_dir)
    file_path = get_file_path(download_dir)
    logger.info(file_path)
    transform_data(file_path, month_str)
    # upload_to_firefly(file_path)
