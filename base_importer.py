
import logging
import os
import re
import shutil
import subprocess
import unicodedata
from abc import ABC, abstractmethod

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

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
GOTIFY_TOKEN=os.getenv('GOTIFY_TOKEN')

class BaseImporter(ABC):

    def __init__(self, imports_dir):
        self.import_dir = imports_dir

    def copy_template(self):
        class_name = self.__class__.__name__
        output_path = os.path.join(self.import_dir, class_name + '.json')
        script_path = os.path.dirname(os.path.realpath(__file__))
        config_path = os.path.join(script_path, class_name + "_config.json")
        shutil.copyfile(config_path, os.path.join(self.import_dir, output_path))
        logger.info(f'JSON Import config copied to import directory: {self.import_dir}')

    def empty_imports(self):
        """Empty the import directory"""
        if os.path.exists(self.import_dir):
            shutil.rmtree(self.import_dir)
        os.makedirs(self.import_dir, exist_ok=True)
        
    
    def upload_to_firefly(self):
        completed_process = subprocess.run([
        "docker", "run",
        "--rm",
        "-v", f"{self.import_dir}:/import",
        "-e", f"FIREFLY_III_ACCESS_TOKEN={TOKEN}",
        "-e", "IMPORT_DIR_ALLOWLIST=/import",
        "-e", f"FIREFLY_III_URL={HOME_IP}:8995",
        "-e", "WEB_SERVER=false",
        "fireflyiii/data-importer:develop"
        ], capture_output=True, text=True)
        logger.info("Output: %s", completed_process.stdout)
        logger.info("Error: %s}" ,completed_process.stderr)

    
    def notify(self, header, message):
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

    def to_csv(self, df):
        class_name = self.__class__.__name__
        output_path = os.path.join(self.import_dir, class_name + '.csv')
        rows = len(df)
        logger.info(f"Number of rows in df: {rows}")
        df.to_csv(output_path)
        logger.info(f'Saved to path {output_path}')

    def is_japanese(self, string):
        if bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u30FC]', string)):
            return string
        else:
            return ''
    
    def translate(self, text):
        # use chatgpt to translate text from japanese to english
        prompt =  f"Translate to english '{text}' from the perspective of converting a shopping merchant name."
        response = client.completions.create(model="gpt-3.5-turbo-instruct", prompt=prompt, temperature=0.2)
        translated_text = response.choices[0].text.strip()
        logger.info(f'Translate: {text} to {translated_text}')
        return translated_text.replace('"', '')

    def normalize_text(self, text):
        return unicodedata.normalize('NFKC', text)

    def handle_pure_japanese(self, df):
        # Where Notes column contains a value, use ChatGpt API to translate the value to English and replace the value in the Name column with the translated value.
        df['Notes'] = df['Name'].apply(self.is_japanese)
        # for rows that have a value in Notes column, send this value to translate function and replace the value in the Name column with the translated value.
        df.loc[df['Notes'] != '', 'Name'] = df.loc[df['Notes'] != '', 'Notes'].apply(self.translate)    
        return df
    
    def apply_normalization(self, df):
        df['Name'] = df['Name'].apply(self.normalize_text)
        return df
    
        
    @abstractmethod
    def run(self):
        pass


