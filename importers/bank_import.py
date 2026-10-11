import calendar
import datetime
import logging
import os
import re
import subprocess
import random
import time
from logging.handlers import RotatingFileHandler

import pandas as pd
from dotenv import load_dotenv
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

from importers.base_importer import BaseImporter

load_dotenv()

USER = os.getenv("BANK_ACCOUNT_USER")
PASSWORD = os.getenv("BANK_ACCOUNT_PASSWORD")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR")
OUTPUT_PATH = os.getenv("OUTPUT_PATH")
BANK_IMPORTS_DIR = os.getenv("BANK_IMPORTS_DIR")


class BankImporter(BaseImporter):
    def run(self):
        self.empty_imports()
        month_end = datetime.date.today()
        month_start = month_end - datetime.timedelta(days=14)
        self.logger.info(f"Start Date: {month_start}")
        self.logger.info(f"End Date: {month_end}")
        try:
            self.logger.info("downloading from bank")
            self.download_bank_csv(month_start, month_end, DOWNLOAD_DIR)
        except:
            self.notify("FF3_IMPORT", "Bank data import failed during Selenium phase.")
            raise

        file_path = self.get_file_path(DOWNLOAD_DIR)
        self.logger.info(f"Using latest download file: {file_path}")
        assert file_path.endswith(".csv"), "File is not a csv file"
        output_path = os.path.join(self.import_dir, "bank_export")
        try:
            self.transform_data(file_path, output_path + ".csv")
        except:
            self.notify("FF3_IMPORT", "Bank data import failed during transform phase.")
            raise
        # copy files including json file into import dir with correct names. First clean out any old files from earlier runs.
        self.copy_template()
        try:
            self.logger.info("upload")
            self.upload_to_firefly()
        except:
            self.notify("FF3_IMPORT", "Bank data import failed during upload phase.")
            raise

    def get_file_path(self, download_dir):
        """From the download directory get the file path of the downloaded file based on selecting the most recently saved file."""
        files = os.listdir(download_dir)
        if not files:
            raise Exception(f"No files found in download directory: {download_dir}")
        # filter for csv files
        files = [f for f in files if f.endswith(".csv")]
        if not files:
            raise Exception(f"No csv files found in download directory: {download_dir}")
        files.sort(key=lambda x: os.path.getmtime(os.path.join(download_dir, x)))
        file_path = os.path.join(download_dir, files[-1])
        return file_path

    def download_bank_csv(self, month_start, month_end, download_dir):
        """Use undetected-chromedriver to download csv file from bank account"""
        month_start_str = month_start.strftime("%Y/%m/%d")
        month_end_str = month_end.strftime("%Y/%m/%d")

        options = uc.ChromeOptions()
        options.binary_location = os.getenv(
            "CHROME_BINARY", "/usr/bin/google-chrome"
        )
        # Disabling headless often bypasses Access Denied on servers
        # options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        
        # Prefs for download
        options.add_experimental_option(
            "prefs",
            {
                "download.default_directory": download_dir,
            },
        )
        
        chrome_version = subprocess.check_output(
            [options.binary_location, "--version"], text=True
        ).strip()
        match = re.search(r"(\d+)\.", chrome_version)
        if not match:
            raise RuntimeError(f"Could not determine Chrome version: {chrome_version}")
        chrome_major = int(match.group(1))

        self.logger.info(
            "Starting undetected-chromedriver for Chrome major version %s...",
            chrome_major,
        )
        driver = uc.Chrome(options=options, version_main=chrome_major)

        try:
            # The bank's anti-bot layer (Akamai) intermittently returns an
            # "Access Denied" page after sign-on, so retry the whole login a
            # few times before giving up.
            max_login_attempts = 4
            all_arrow_links = []
            for attempt in range(1, max_login_attempts + 1):
                self.logger.info(
                    f"Navigating to login page... (attempt {attempt}/{max_login_attempts})"
                )
                driver.get(
                    "https://login.smbctb.co.jp/ib/portal/POSNIN1prestiatop.prst?LOCALE=en_JP"
                )

                time.sleep(random.uniform(5, 8))

                try:
                    user_field = driver.find_element(By.ID, "dispuserId")
                    pass_field = driver.find_element(By.ID, "disppassword")
                except Exception as e:
                    self.logger.error(f"Could not find login fields. Page Title: {driver.title}")
                    raise e

                # Type like a human
                for char in USER:
                    user_field.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.2))

                time.sleep(random.uniform(0.5, 1.5))

                for char in PASSWORD:
                    pass_field.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.2))

                self.logger.info("Credentials entered. Submitting form...")
                time.sleep(2)

                # The login page now contains a hidden duplicate "Sign On"
                # link, so target the visible button by its class instead.
                try:
                    login_button = driver.find_element(
                        By.CSS_SELECTOR, "a.btn.btn-large.btn-inverse"
                    )
                    self.logger.info(
                        f"Found login button: {login_button.text}. Clicking..."
                    )
                    login_button.click()
                except Exception as e:
                    self.logger.warning(
                        f"Could not click login button: {e}. "
                        "Falling back to the page's own submit helper..."
                    )
                    driver.execute_script(
                        "submitProc(); doTransaction('/portal/POSNIN1next', null, false, null, POSNIN1, null, null);"
                    )

                self.logger.info("Waiting for dashboard...")
                time.sleep(15)

                self.logger.info(f"Page Title after login: {driver.title}")
                self.logger.info(f"Current URL: {driver.current_url}")

                if "Access Denied" in driver.title:
                    self.logger.warning(
                        f"Access Denied after login (attempt {attempt}). Retrying..."
                    )
                    time.sleep(random.uniform(8, 15))
                    continue

                # Look for navigation links
                all_arrow_links = driver.find_elements(
                    By.CSS_SELECTOR, "a.link-arrow"
                )
                if all_arrow_links:
                    break

                self.logger.warning(
                    f"No 'link-arrow' elements found on attempt {attempt}. Retrying..."
                )
                time.sleep(random.uniform(8, 15))

            if not all_arrow_links:
                self.logger.warning("No 'link-arrow' elements found. Listing all links on page:")
                all_links = driver.find_elements(By.TAG_NAME, "a")
                for i, l in enumerate(all_links):
                    t = l.text.strip()
                    if t:
                        self.logger.info(f"Link {i}: {t}")
                raise Exception("Could not find navigation links on dashboard.")

            # Identify the Download Account Activities link
            link = None
            for l in all_arrow_links:
                if "Download Account Activities" in l.text:
                    link = l
                    break

            if not link and len(all_arrow_links) >= 4:
                # Fallback to the historical index if text match fails
                link = all_arrow_links[3]

            if not link:
                raise Exception("Could not identify the Download Account Activities link.")

            self.logger.info(f"Clicking link: {link.text}")
            link.click()
            time.sleep(5)

            # fill in the form
            from_field = driver.find_element(By.NAME, "tradingHistoryPeriodFrom")
            up_to_field = driver.find_element(By.NAME, "tradingHistoryPeriodTo")

            from_field.clear()
            from_field.send_keys(month_start_str)
            up_to_field.clear()
            up_to_field.send_keys(month_end_str)
            time.sleep(2)

            submit_button = driver.find_element(
                By.CSS_SELECTOR, "a.btn.btn-small.btn-download"
            )
            submit_button.click()
            self.logger.info("Download triggered. Waiting for file...")
            time.sleep(10)
        finally:
            driver.quit()

    def transform_data(self, file_path, output_path):
        """Read csv file path with pandas and change encoding from shift-jis to utf-8.
        Then save file to csv."""
        self.logger.info(f"Beginning Transform...")
        column_names = ["Date", "Destination", "Amount", "Ignore"]
        df = pd.read_csv(
            file_path, encoding="shift_jis", header=None, names=column_names
        )
        df["Amount"] = df.apply(
            lambda row: row["Amount"].replace("-", "")
            if "REMITTANCE" in row["Destination"]
            else row["Amount"],
            axis=1,
        )
        self.to_csv(df)


def main():
    bi = BankImporter(BANK_IMPORTS_DIR)
    bi.run()


if __name__ == "__main__":
    main()
