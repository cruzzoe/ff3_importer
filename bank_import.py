import calendar
import datetime
import logging
import os
import time
from logging.handlers import RotatingFileHandler

import pandas as pd
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from base_importer import BaseImporter

load_dotenv()

USER=os.getenv("BANK_ACCOUNT_USER")
PASSWORD=os.getenv("BANK_ACCOUNT_PASSWORD")
DOWNLOAD_DIR=os.getenv("DOWNLOAD_DIR")
OUTPUT_PATH=os.getenv("OUTPUT_PATH")
BANK_IMPORTS_DIR=os.getenv("BANK_IMPORTS_DIR")

class BankImporter(BaseImporter):

    def run(self):
        self.notify('FF3_IMPORT', 'About to fetch bank data and import into FF3...')
        self.empty_imports()
        current_month = datetime.datetime.today()
        previous_month = current_month 
        last_day = datetime.datetime.today().day
        # _, last_day = calendar.monthrange(previous_month.year, previous_month.month)
        month_str = previous_month.strftime("%B")
        self.logger.info(previous_month)
        month_start = datetime.datetime(previous_month.year, previous_month.month, 1)
        month_end = datetime.datetime(previous_month.year, previous_month.month, last_day)
        self.logger.info(f'Start Date: {month_start}')
        self.logger.info(f'End Date: {month_end}')
        try:
            self.logger.info('downloading from bank')
            self.download_bank_csv(month_start, month_end, DOWNLOAD_DIR)
        except:
            self.notify('FF3_IMPORT', 'Bank data import failed during Selenium phase.')
            raise
        
        file_path = self.get_file_path(DOWNLOAD_DIR)
        self.logger.info(f'Using latest download file: {file_path}')
        assert file_path.endswith('.csv'), 'File is not a csv file'
        output_path = os.path.join(self.import_dir, 'bank_export_' + month_str.lower())
        try:
            self.transform_data(file_path, output_path + '.csv')
        except:
            self.notify('FF3_IMPORT', 'Bank data import failed during transform phase.')
            raise
        # copy files including json file into import dir with correct names. First clean out any old files from earlier runs.
        self.copy_template()
        try:
            self.logger.info('upload')
            self.upload_to_firefly()
        except:
            self.notify('FF3_IMPORT', 'Bank data import failed during upload phase.')
            raise
        self.notify('FF3_IMPORT', f'Bank data imported sucessfully')

    def get_file_path(self,download_dir):
        """From the download directory get the file path of the downloaded file based on selecting the most recently saved file."""
        files = os.listdir(download_dir)
        files.sort(key=lambda x: os.path.getmtime(os.path.join(download_dir, x)))
        file_path = os.path.join(download_dir, files[-1])
        return file_path


    def download_bank_csv(self, month_start, month_end, download_dir):
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
        chrome_options.add_argument("--headless")
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

    def transform_data(self, file_path, output_path):
        """Read csv file path with pandas and change encoding from shift-jis to utf-8.
        Then save file to csv."""
        self.logger.info(f"Beginning Transform...")
        column_names = ["Date", "Destination", "Amount", "Ignore"]
        df = pd.read_csv(file_path, encoding="shift_jis", header=None, names=column_names)
        df['Amount'] = df.apply(lambda row: row['Amount'].replace('-', '') if 'REMITTANCE' in row['Destination'] else row['Amount'], axis=1)
        self.to_csv(df)

def main():
    bi = BankImporter(BANK_IMPORTS_DIR)
    bi.run()

if __name__ == "__main__":
    main()
