import os
import re
import unicodedata
import subprocess
import shutil
import logging
from importers.base_importer import BaseImporter
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CC_IMPORTS_DIR=os.getenv("CC_IMPORTS_DIR")

class CreditCardImporter(BaseImporter):
    
    def run(self):
        # self.download()
        self.notify('FF3_IMPORT', 'About to fetch credit data and import into FF3...')
        self.empty_imports()
        os.makedirs(self.import_dir, exist_ok=True)
        with open('/Users/cruzoe/Downloads/card_dec_statement.html', 'r') as f:
            content = f.read()

        df = self.html_to_df(content)
        df = self.remove_non_transactions(df)
        df = self.handle_square_payments(df)
        df = self.make_amounts_negative(df)
        df = self.handle_pure_japanese(df)
        df = self.apply_category(df) 
        df = self.apply_normalization(df)
        rows = len(df)
        self.logger.info(f"Number of rows in df: {rows}")
        self.to_csv(df)
        self.copy_template()
        self.upload_to_firefly()
        self.notify('FF3_IMPORT', f'Credit data imported sucessfully with {rows} rows')

    def html_to_df(self, html):
        df = pd.read_html(html)[2]
        df.columns = ['Ignore0', 'Date', 'Name', 'Amount', 'ignore1', 'ignore2', 'ignore3', 'Description', 'ignore4', 'Ignore5', 'Ignore6', 'Ignore7']
        cols_to_drop = df.columns[df.columns.str.contains('ignore'  , case=False)]
        df = df.drop(columns=cols_to_drop)    
        return df

    def remove_non_transactions(self, df):
        df = df.iloc[1:]
        return df

    def handle_square_payments(self, df):
        # remove the Sq* from the description column
        df['Description'] = df['Description'].str.replace('SQ*', '')
        # if column description contains '*Sq', then replace the value in column name with the value in column description
        df.loc[df['Name'] == 'Square', 'Name'] = df['Description']
        return df

    def make_amounts_negative(self, df):
        # negate the sign on column amount
        df['Amount'] = '-'+df['Amount'].astype(str)
        return df


    def categorize(self, merchant):
        # use chatgpt to select an appropriate category for the merchant
        prompt =  f"Select an appropriate category for shopping merchant {merchant} from: restaurant, drinking, groceries, entertainment, pet, hobbies, coffee, amazon, transportation, utilities, healthcare, online services, home improvement, fitness, insurance, education, unknown. Return only one category name."
        response = client.completions.create(model="gpt-3.5-turbo-instruct", prompt=prompt, temperature=0)
        category = response.choices[0].text.strip().lower()
        self.logger.info(f'Selected merchant: {merchant} to {category}')
        return category.capitalize()

    def apply_category(self, df):
        """For each row in the df, use the categorize function to select an appropriate category for the merchant based on column Name"""
        df['Category'] = df['Name'].apply(self.categorize)
        return df


def main():
    cc = CreditCardImporter(CC_IMPORTS_DIR)
    cc.run()
 

if __name__ == '__main__':
    main()