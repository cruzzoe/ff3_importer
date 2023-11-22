import os
import re
import unicodedata
import subprocess
import shutil
import logging

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

TOKEN = os.getenv("TOKEN")
HOME_IP = os.getenv("HOME_IP")
DOWNLOAD_DIR=os.getenv("DOWNLOAD_DIR")
CC_IMPORTS_DIR=os.getenv("CC_IMPORTS_DIR")
GOTIFY_TOKEN=os.getenv('GOTIFY_TOKEN')

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


def empty_imports(imports):
    """Empty the import directory"""
    if os.path.exists(imports):
        shutil.rmtree(imports)
        
def is_japanese(string):
    if bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u30FC]', string)):
        return string
    else:
        return ''

def html_to_df(html):
    df = pd.read_html(html)[2]
    df.columns = ['Ignore0', 'Date', 'Name', 'Amount', 'ignore1', 'ignore2', 'ignore3', 'Description', 'ignore4', 'Ignore5', 'Ignore6', 'Ignore7']
    cols_to_drop = df.columns[df.columns.str.contains('ignore'  , case=False)]
    df = df.drop(columns=cols_to_drop)    
    return df

def remove_non_transactions(df):
    df = df.iloc[1:3]
    return df

def handle_square_payments(df):
    # remove the Sq* from the description column
    df['Description'] = df['Description'].str.replace('ＳＱ＊', '')
    # if column description contains '*Sq', then replace the value in column name with the value in column description
    df.loc[df['Name'].str.contains('Ｓｑｕａｒｅ'), 'Name'] = df['Description']
    return df

def make_amounts_negative(df):
    # negate the sign on column amount
    df['Amount'] = '-'+df['Amount'].astype(str)
    return df

def translate(text):
    # use chatgpt to translate text from japanese to english
    prompt =  f"Translate to english '{text}' from the perspective of converting a shopping merchant name."
    response = client.completions.create(model="gpt-3.5-turbo-instruct", prompt=prompt, temperature=0.2)
    translated_text = response.choices[0].text.strip()
    logger.info(f'Translate: {text} to {translated_text}')
    return translated_text.replace('"', '')

def normalize_text(text):
    return unicodedata.normalize('NFKC', text)

def handle_pure_japanese(df):
    # Where Notes column contains a value, use ChatGpt API to translate the value to English and replace the value in the Name column with the translated value.
    df['Notes'] = df['Name'].apply(is_japanese)
    # for rows that have a value in Notes column, send this value to translate function and replace the value in the Name column with the translated value.
    df.loc[df['Notes'] != '', 'Name'] = df.loc[df['Notes'] != '', 'Notes'].apply(translate)    
    return df

def categorize(merchant):
    # use chatgpt to select an appropriate category for the merchant
    prompt =  f"Select an appropriate category for shopping merchant {merchant} from: restaurant, drinking, groceries, entertainment, pet, hobbies, coffee, amazon, transportation, utilities, healthcare, online services, home improvement, fitness, insurance, education, unknown. Return only one category name."
    response = client.completions.create(model="gpt-3.5-turbo-instruct", prompt=prompt, temperature=0)
    category = response.choices[0].text.strip().lower()
    logger.info(f'Selected merchant: {merchant} to {category}')
    return category.capitalize()

def apply_category(df):
    """For each row in the df, use the categorize function to select an appropriate category for the merchant based on column Name"""
    df['Category'] = df['Name'].apply(categorize)
    return df

def apply_normalization(df):
    df['Name'] = df['Name'].apply(normalize_text)
    return df


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
    logger.info("Output:", completed_process.stdout)
    logger.info("Error:", completed_process.stderr)

def copy_template(imports_dir, filename):
    script_path = os.path.dirname(os.path.realpath(__file__))
    config_path = os.path.join(script_path, "credit_card_config.json")
    filename = filename.split('/')[-1].split('.')[0]
    shutil.copyfile(config_path, os.path.join(imports_dir, filename + '.json'))
    logger.info(f'JSON Import config copied to import directory: {imports_dir}')


def main():
    notify('FF3_IMPORT', 'About to fetch bank data and import into FF3...')
    imports_dir = CC_IMPORTS_DIR 
    empty_imports(imports_dir)
    os.makedirs(imports_dir, exist_ok=True)
    # TODO how to src latest extraction filename?
    with open('table_export.html', 'r') as f:
        content = f.read()
    df = html_to_df(content)
    df = remove_non_transactions(df)
    df = handle_square_payments(df)
    df = make_amounts_negative(df)
    df = handle_pure_japanese(df)
    df = apply_category(df) 
    df = apply_normalization(df)
    output_path = os.path.join(imports_dir, 'credit_card_export.csv')
    rows = len(df)
    logger.info(f"Number of rows in df: {rows}")
    df.to_csv(output_path)

    # copy files including json file into import dir with correct names. First clean out any old files from earlier runs.
    logger.info(f'Output saved to path {output_path}')
    copy_template(imports_dir, output_path)
    try:
        upload_to_firefly(imports_dir)
    except:
        notify('FF3_IMPORT', 'Bank data import failed during upload phase.')
        raise
    notify('FF3_IMPORT', f'Bank data imported sucessfully with {rows} rows')

if __name__ == '__main__':
    main()