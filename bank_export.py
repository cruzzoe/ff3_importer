import datetime
import os
import subprocess
import time
import calendar
import shutil
import logging

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
OUTPUT_PATH=os.getenv("OUTPUT_PATH")
BANK_IMPORTS_DIR=os.getenv("BANK_IMPORTS_DIR")
GOTIFY_TOKEN=os.getenv('GOTIFY_TOKEN')
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
    cmd = f'curl "http://{HOME_IP}:8991/message?token={GOTIFY_TOKEN}" -F "title=[{header}]" -F "message"="{message}" -F "priority=5"'
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
    time.sleep(3)
    driver.quit()


def upload_to_firefly(imports_dir):
    completed_process = subprocess.run([
    "docker", "run",
    "--rm",
    "-v", f"{imports_dir}:/import",
    "-e", f"FIREFLY_III_ACCESS_TOKEN={TOKEN}",
    "-e", "IMPORT_DIR_ALLOWLIST=/import",
    "-e", f"FIREFLY_III_URL={HOME_IP}:8995",
    "-e", "WEB_SERVER=false",
    "fireflyiii/data-importer:develop"
    ], capture_output=True, text=True)
    print("Output:", completed_process.stdout)
    print("Error:", completed_process.stderr)


def transform_data(file_path, output_path):
    """Read csv file path with pandas and change encoding from shift-jis to utf-8.
    Then save file to csv."""
    logger.info(f"Beginning Transform...")
    column_names = ["Date", "Destination", "Amount", "Ignore"]
    df = pd.read_csv(file_path, encoding="shift_jis", header=None, names=column_names)
    df['Amount'] = df.apply(lambda row: row['Amount'].replace('-', '') if 'REMITTANCE' in row['Destination'] else row['Amount'], axis=1)
    df.to_csv(output_path, encoding="utf-8")
    logger.info(f"File saved down to target: {output_path}")
    rows = len(df)
    logger.info(f"Number of rows in df: {rows}")
    return rows

def empty_imports(imports):
    """Empty the import directory"""
    if os.path.exists(imports):
        shutil.rmtree(imports)

def copy_template(imports_dir, filename):
    script_path = os.path.dirname(os.path.realpath(__file__))
    config_path = os.path.join(script_path, "bank_config.json")
    shutil.copyfile(config_path, os.path.join(imports_dir, filename + '.json'))
    logger.info(f'JSON Import config copied to import directory: {imports_dir}')

if __name__ == "__main__":
    notify('FF3_IMPORT', 'About to fetch bank data and import into FF3...')
    imports_dir = BANK_IMPORTS_DIR 
    empty_imports(imports_dir)
    os.makedirs(imports_dir, exist_ok=True)
    current_month = datetime.datetime.today()
    previous_month = current_month - datetime.timedelta(days=30)
    _, last_day = calendar.monthrange(previous_month.year, previous_month.month)

    month_str = previous_month.strftime("%B")
    logger.info(previous_month)
    month_start = datetime.datetime(previous_month.year, previous_month.month, 1)
    month_end = datetime.datetime(previous_month.year, previous_month.month, last_day)
    logger.info(f'Start Date: {month_start}')
    logger.info(f'End Date: {month_end}')
    try:
        download_bank_csv(month_start, month_end, DOWNLOAD_DIR)
    except:
        notify('FF3_IMPORT', 'Bank data import failed during Selenium phase.')
        raise
    file_path = get_file_path(DOWNLOAD_DIR)
    logger.info(f'Using latest download file: {file_path}')
    assert file_path.endswith('.csv'), 'File is not a csv file'
    output_path = os.path.join(imports_dir, 'bank_export_' + month_str.lower())
    try:
        rows = transform_data(file_path, output_path + '.csv')
    except:
        notify('FF3_IMPORT', 'Bank data import failed during transform phase.')
        raise
    # copy files including json file into import dir with correct names. First clean out any old files from earlier runs.
    copy_template(imports_dir, output_path)
    try:
        upload_to_firefly(imports_dir)
    except:
        notify('FF3_IMPORT', 'Bank data import failed during upload phase.')
        raise
    notify('FF3_IMPORT', 'Bank data imported sucessfully with {rows} rows')
