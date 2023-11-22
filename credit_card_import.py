import os
import re
import unicodedata
import subprocess
import shutil
import logging
from base_importer import BaseImporter
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
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

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CC_IMPORTS_DIR=os.getenv("CC_IMPORTS_DIR")

class CreditCardImporter(BaseImporter):
    
    def run(self):
        # self.download()
        self.notify('FF3_IMPORT', 'About to fetch bank data and import into FF3...')
        self.empty_imports()
        os.makedirs(self.import_dir, exist_ok=True)
        # TODO how to src latest extraction filename?
        with open('table_export.html', 'r') as f:
            content = f.read()

        df = self.html_to_df(content)
        df = self.remove_non_transactions(df)
        df = self.handle_square_payments(df)
        df = self.make_amounts_negative(df)
        df = self.handle_pure_japanese(df)
        df = self.apply_category(df) 
        df = self.apply_normalization(df)
        output_path = os.path.join(self.import_dir, 'credit_card_export.csv')
        rows = len(df)
        logger.info(f"Number of rows in df: {rows}")
        df.to_csv(output_path)

        # copy files including json file into import dir with correct names. First clean out any old files from earlier runs.
        logger.info(f'Output saved to path {output_path}')
        self.copy_template()
        try:
            print('uploading')
            # self.upload_to_firefly(self.import_dir)
        except:
            self.notify('FF3_IMPORT', 'Bank data import failed during upload phase.')
            raise
        self.notify('FF3_IMPORT', f'Bank data imported sucessfully with {rows} rows')

    def html_to_df(self, html):
        df = pd.read_html(html)[2]
        df.columns = ['Ignore0', 'Date', 'Name', 'Amount', 'ignore1', 'ignore2', 'ignore3', 'Description', 'ignore4', 'Ignore5', 'Ignore6', 'Ignore7']
        cols_to_drop = df.columns[df.columns.str.contains('ignore'  , case=False)]
        df = df.drop(columns=cols_to_drop)    
        return df

    def remove_non_transactions(self, df):
        df = df.iloc[1:3]
        return df

    def handle_square_payments(self, df):
        # remove the Sq* from the description column
        df['Description'] = df['Description'].str.replace('ＳＱ＊', '')
        # if column description contains '*Sq', then replace the value in column name with the value in column description
        df.loc[df['Name'].str.contains('Ｓｑｕａｒｅ'), 'Name'] = df['Description']
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
        logger.info(f'Selected merchant: {merchant} to {category}')
        return category.capitalize()

    def apply_category(self, df):
        """For each row in the df, use the categorize function to select an appropriate category for the merchant based on column Name"""
        df['Category'] = df['Name'].apply(self.categorize)
        return df


def main():
    cc = CreditCardImporter('/Users/cruzoe/firefly_imports/cc')
    cc.run()
 

if __name__ == '__main__':
    main()