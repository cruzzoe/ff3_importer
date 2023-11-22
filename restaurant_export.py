# restarant card importer

from base_importer import BaseImporter
import datetime
import os
import time
from bs4 import BeautifulSoup
import pandas as pd
from collections import namedtuple

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from logging.handlers import RotatingFileHandler

import pandas as pd

load_dotenv()

TOKEN = os.getenv("TOKEN")
HOME_IP = os.getenv("HOME_IP")
DOWNLOAD_DIR=os.getenv("DOWNLOAD_DIR")
GOTIFY_TOKEN=os.getenv('GOTIFY_TOKEN')
RESTAURANT_USER=os.getenv('RESTAURANT_USER')
RESTAURANT_PASSWORD=os.getenv('RESTAURANT_PASSWORD')
RESTAURANT_IMPORTS_DIR=os.getenv('RESTAURANT_IMPORTS_DIR')


class RestaurantCardImporter(BaseImporter):
    
    def _init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def download_transactions(self):
        chrome_options = Options()
        # chrome_options.add_experimental_option()
        driver = webdriver.Chrome(options=chrome_options)
        driver.get('https://myedenred.jp/TRT/TopPage')
        driver.implicitly_wait(0.5)
        driver.find_element(By.NAME, "Username").send_keys(RESTAURANT_USER)
        driver.find_element(By.NAME, "Password").send_keys(RESTAURANT_PASSWORD)
        submit_button = driver.find_element(By.ID, "login")
        submit_button.click()
        time.sleep(7)
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

        df = pd.DataFrame(data)
        # filter df to only include rows which belong to the month we are importing. 
        df['Date_obj'] = pd.to_datetime(df['Date'])
        df['Month'] = df['Date_obj'].dt.month
        df_fitered = df[df['Month'] == month_int]
        df_fitered = df_fitered.drop(columns=['Month', 'Date_obj'])
        # logger.debug(df)
        return df_fitered

    def run(self):
        self.empty_imports()
        # Selenium scrape the data
        soup = self.download_transactions()
        month = datetime.date.today() - datetime.timedelta(days=15)
        month_int = month.month
        df = self.transform(soup, month_int)
        df = self.handle_pure_japanese(df)
        df = self.apply_normalization(df)
        df.Amount = df.Amount.str.replace('円', '')
        self.to_csv(df)
        self.copy_template(self.import_dir)
        self.upload_to_firefly()

# rc = RestaurantCardImporter(RESTAURANT_IMPORTS_DIR)

# rc.run()