# restarant card importer

import datetime
import os
import time
from collections import namedtuple
from logging.handlers import RotatingFileHandler

import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from importers.base_importer import BaseImporter

load_dotenv()
DOWNLOAD_DIR=os.getenv("DOWNLOAD_DIR")
RESTAURANT_USER=os.getenv('RESTAURANT_USER')
RESTAURANT_PASSWORD=os.getenv('RESTAURANT_PASSWORD')
RESTAURANT_IMPORTS_DIR=os.getenv('RESTAURANT_IMPORTS_DIR')

class RestaurantCardImporter(BaseImporter):
    
    def _init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def download_transactions(self):
        chrome_options = Options()
        # chrome_options.add_experimental_option()
        # chrome_options.add_argument("--headless")
        chrome_options.add_experimental_option(
        # On Mac - Chrome prompts to download the file if default directory is changed.
        # I dont think this happens on ubuntu
            "prefs",
            {
                "download.default_directory": DOWNLOAD_DIR,
                # "safebrowsing.enabled": True,
                # "download.prompt_for_download": False,
                # "safebrowsing_for_trusted_sources_enabled": False
            },
        )
        driver = webdriver.Chrome(options=chrome_options)
        driver.get('https://myedenred.jp/TRT/TopPage')
        driver.implicitly_wait(0.5)
        driver.find_element(By.NAME, "Username").send_keys(RESTAURANT_USER)
        driver.find_element(By.NAME, "Password").send_keys(RESTAURANT_PASSWORD)
        submit_button = driver.find_element(By.ID, "login")
        submit_button.click()
        time.sleep(15)
        html = driver.page_source
        # Parse the HTML content using BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        return soup


    def transform(self, soup, month_int):
        """Transform the data into a dataframe"""
        tables = soup.find_all("table")
        data = []
        RowData = namedtuple('RowData', ['Date','Name', 'Amount'])

        for table in tables:
            date = table.find("thead").get_text(strip=True)
            rows = table.find("tbody").find_all("tr")
            for row in rows:
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    th_text = th.get_text(strip=True)
                    td_text = td.get_text(strip=True)
                    if td_text != '0円':  # Skip if transaction is '0 Yen'
                        if th_text == '内容':  # If content is '内容', td_text is the merchant
                            merchant = td_text
                        elif th_text == '出金':  # If content is '出金', td_text is the amount
                            amount = td_text
                            # Create a RowData named tuple and append it to the data list
                            amount = '-' + amount
                            row_data = RowData(Date=date, Name=merchant, Amount=amount)
                            data.append(row_data)
                        else:
                            amount = td_text
                            amount = amount
                            row_data = RowData(Date=date, Name=merchant, Amount=amount)
                            data.append(row_data)

        df = pd.DataFrame(data)
        self.logger.info(df)
        # filter df to only include rows which belong to the month we are importing. 
        df['Date_obj'] = pd.to_datetime(df['Date'])
        df['Month'] = df['Date_obj'].dt.month
        df_fitered = df[df['Month'] == month_int]
        df_fitered = df_fitered.drop(columns=['Month', 'Date_obj'])
        self.logger.debug(df_fitered)
        return df_fitered

    def run(self):
        self.empty_imports()
        # Selenium scrape the data
        soup = self.download_transactions()
        month = datetime.date.today()
        month_int = month.month
        df = self.transform(soup, month_int)
        df = self.handle_pure_japanese(df)
        df = self.apply_normalization(df)
        df.Amount = df.Amount.str.replace('円', '')
        df = self.create_unique_id(df)
        self.to_csv(df)
        self.copy_template()
        self.upload_to_firefly()

if __name__ == "__main__":
    rc = RestaurantCardImporter(RESTAURANT_IMPORTS_DIR)
    rc.run()    
