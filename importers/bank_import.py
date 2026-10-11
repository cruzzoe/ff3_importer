import calendar
import datetime
import logging
import os
import re
import subprocess
import random
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

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
            file_path = self.download_bank_csv(month_start, month_end, DOWNLOAD_DIR)
        except:
            self.notify("FF3_IMPORT", "Bank data import failed during Selenium phase.")
            raise

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

    @staticmethod
    def _download_link(driver):
        # Select by meaning rather than a position that can change with the UI.
        for link in driver.find_elements(By.CSS_SELECTOR, "a.link-arrow"):
            if ("Download Account Activities" in link.text
                    and link.is_displayed() and link.is_enabled()):
                return link
        return False

    @staticmethod
    def _access_denied(driver):
        return "access denied" in driver.title.casefold()

    def _login(self, driver, wait, max_attempts, retry_delay):
        for attempt in range(1, max_attempts + 1):
            self.logger.info("Opening bank login (attempt %s/%s)", attempt, max_attempts)
            try:
                driver.get(
                    "https://login.smbctb.co.jp/ib/portal/POSNIN1prestiatop.prst?LOCALE=en_JP"
                )
                # Check for a denial before submitting credentials as well.
                user_field = wait.until(lambda d: "denied" if self._access_denied(d)
                                        else EC.element_to_be_clickable((By.ID, "dispuserId"))(d))
                if user_field == "denied":
                    outcome = "denied"
                else:
                    pass_field = wait.until(EC.element_to_be_clickable((By.ID, "disppassword")))
                    user_field.clear()
                    pass_field.clear()
                    user_field.send_keys(USER)
                    pass_field.send_keys(PASSWORD)
                    login_button = wait.until(EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "a.btn.btn-large.btn-inverse")
                    ))
                    login_button.click()
                    self.logger.info("Sign-on submitted; waiting for download navigation")
                    outcome = wait.until(lambda d: "denied" if self._access_denied(d)
                                         else self._download_link(d))
            except TimeoutException:
                # Do not resubmit on an unknown result: it could be MFA,
                # rejected credentials, a changed UI, or a slow response.
                raise RuntimeError(
                    "Bank login timed out waiting for expected controls. "
                    "No further sign-on attempted; check manually for a login error, "
                    "verification prompt, or changed bank page."
                ) from None

            if outcome != "denied":
                self.logger.info("Bank download navigation is ready")
                return outcome

            self.logger.warning("Bank returned Access Denied (attempt %s/%s)",
                                attempt, max_attempts)
            if attempt == max_attempts:
                raise RuntimeError(
                    f"Bank returned Access Denied after {max_attempts} attempt(s); "
                    "no CSV downloaded. Check normal browser access on this network."
                )
            delay = retry_delay * (2 ** (attempt - 1)) + random.uniform(0, 5)
            self.logger.info("Waiting %.1f seconds before retrying denied access", delay)
            time.sleep(delay)

    @staticmethod
    def _csv_snapshot(download_dir):
        return {p: (p.stat().st_mtime_ns, p.stat().st_size)
                for p in Path(download_dir).glob("*.csv") if p.is_file()}

    def _new_csv(self, download_dir, before):
        # Chrome renames a .crdownload to .csv when the download completes.
        current = self._csv_snapshot(download_dir)
        changed = [p for p, signature in current.items()
                   if signature != before.get(p) and signature[1] > 0
                   and not Path(str(p) + ".crdownload").exists()]
        return str(max(changed, key=lambda p: current[p][0])) if changed else False

    def download_bank_csv(self, month_start, month_end, download_dir):
        """Download a fresh CSV, with bounded retries and credential-free diagnostics."""
        # These settings are deliberately read independently of credential files.
        max_attempts = int(os.getenv("BANK_LOGIN_ATTEMPTS", "2"))
        retry_delay = float(os.getenv("BANK_LOGIN_RETRY_SECONDS", "60"))
        wait_seconds = float(os.getenv("BANK_PAGE_TIMEOUT_SECONDS", "45"))
        download_seconds = float(os.getenv("BANK_DOWNLOAD_TIMEOUT_SECONDS", "120"))
        if not 1 <= max_attempts <= 4:
            raise ValueError("BANK_LOGIN_ATTEMPTS must be between 1 and 4")
        if not 30 <= retry_delay <= 600:
            raise ValueError("BANK_LOGIN_RETRY_SECONDS must be between 30 and 600")
        if not 1 <= wait_seconds <= 300 or not 1 <= download_seconds <= 600:
            raise ValueError("Bank page/download timeouts are outside supported bounds")
        if not USER or not PASSWORD:
            raise RuntimeError("Bank login credentials are not configured")
        if not download_dir:
            raise RuntimeError("Bank download directory is not configured")
        download_dir = os.path.abspath(download_dir)
        os.makedirs(download_dir, exist_ok=True)

        options = uc.ChromeOptions()
        options.binary_location = os.getenv("CHROME_BINARY", "/usr/bin/google-chrome")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_experimental_option("prefs", {"download.default_directory": download_dir})
        chrome_version = subprocess.check_output(
            [options.binary_location, "--version"], text=True
        ).strip()
        match = re.search(r"(\d+)\.", chrome_version)
        if not match:
            raise RuntimeError("Could not determine Chrome version")
        chrome_major = int(match.group(1))
        self.logger.info("Starting bank browser for Chrome major version %s", chrome_major)
        driver = uc.Chrome(options=options, version_main=chrome_major)
        try:
            driver.set_page_load_timeout(wait_seconds)
            wait = WebDriverWait(driver, wait_seconds, ignored_exceptions=(StaleElementReferenceException,))
            link = self._login(driver, wait, max_attempts, retry_delay)
            link.click()
            from_field = wait.until(EC.element_to_be_clickable((By.NAME, "tradingHistoryPeriodFrom")))
            up_to_field = wait.until(EC.element_to_be_clickable((By.NAME, "tradingHistoryPeriodTo")))
            from_field.clear()
            from_field.send_keys(month_start.strftime("%Y/%m/%d"))
            up_to_field.clear()
            up_to_field.send_keys(month_end.strftime("%Y/%m/%d"))
            submit_button = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "a.btn.btn-small.btn-download")
            ))
            before = self._csv_snapshot(download_dir)
            submit_button.click()
            self.logger.info("Download requested; waiting for a fresh completed CSV")
            try:
                return WebDriverWait(driver, download_seconds).until(
                    lambda _: self._new_csv(download_dir, before)
                )
            except TimeoutException:
                raise RuntimeError(
                    "Bank CSV download timed out; no fresh completed CSV found. "
                    "Existing files will not be imported."
                ) from None
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
