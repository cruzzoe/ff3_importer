import json
import os
import shutil
import time
import pandas as pd
from dotenv import load_dotenv
import google.generativeai as genai

from importers.base_importer import BaseImporter

load_dotenv()

# --- GEMINI CONFIGURATION ---
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# 1. Define your categories clearly
VALID_CATEGORIES = [
    "restaurant", "drinking", "groceries", "entertainment", "pet", "hobbies",
    "coffee", "amazon", "transportation", "utilities", "healthcare",
    "online services", "home improvement", "fitness", "insurance", "education", "unknown"
]

# 2. Define the Categorization Model with "Few-Shot" Logic Rules
system_instruction_categorization = (
    f"You are an expert transaction categorizer. "
    f"You will be given a merchant name. "
    f"You must strictly select the single best category from this list: {', '.join(VALID_CATEGORIES)}. "
    f"Follow these logic rules:\n"
    f"1. Izakaya / Bars / Pubs -> 'Drinking'\n"
    f"2. Convenience Stores (7-11, Lawson, FamilyMart) -> 'Groceries'\n"
    f"3. Drug Stores (Matsumoto Kiyoshi, Welcia) -> 'Healthcare' (unless clearly food only)\n"
    f"4. Suica / Pasmo / JR / Taxi -> 'Transportation'\n"
    f"5. Netflix / Spotify / YouTube / Cinemas -> 'Entertainment'\n"
    f"6. Uniqlo / GU / Zozotown -> 'Hobbies'\n"
    f"Return ONLY the category name. Do not explain."
)

model_categorizer = genai.GenerativeModel(
    model_name="models/gemini-2.5-flash",
    system_instruction=system_instruction_categorization
)

CC_IMPORTS_DIR = os.getenv("CC_IMPORTS_DIR")

class CreditCardImporter(BaseImporter):

    def run(self, file_path):
        # self.download()
        self.notify('FF3_IMPORT', 'About to fetch credit data and import into FF3...')
        os.makedirs(self.import_dir, exist_ok=True)

        # Initialize columns to prevent errors if class name doesn't match
        columns = []
        skiprows = 0

        if self.__class__.__name__ == 'AZ':
            skiprows = 1
            # columns = ['Date', 'Name', '3', '4', '5', '6', 'Amount', '8', '9', '10', '11', '12', '13']
        elif self.__class__.__name__ == 'PST':
            # columns = ['Date', "Name", '3', '4', '5', 'Amount', '7']
            columns = ['Date', 'Name', '3', '4', '5', 'Amount', '7', '8', '9', '10', '11', '12', '13']
            skiprows = 0

        df = pd.read_csv(file_path, encoding='SHIFT_JIS', names=columns, header=None, skiprows=skiprows, encoding_errors='replace')
        print(df.head())

        df = self.handle_square_payments(df)
        df = self.make_amounts_negative(df)

        # This calls BaseImporter.handle_pure_japanese (Update BaseImporter for translation improvements!)
        df = self.handle_pure_japanese(df)

        df = self.apply_category(df)
        df = self.apply_normalization(df)
        df = self.create_unique_id(df)

        rows = len(df)
        self.logger.info(f"Number of rows in df: {rows}")
        self.to_csv(df)
        self.copy_template()
        self.upload_to_firefly()
        
        processed_name = file_path + '.processed'
        shutil.move(file_path, processed_name)
        # self.notify('FF3_IMPORT', f'Credit data imported sucessfully with {rows} rows')

    def remove_non_transactions(self, df):
        df = df.iloc[1:]
        return df

    def handle_square_payments(self, df):
        """Use column 7 as the merchant name for full-width Square rows."""
        if df.shape[1] < 7:
            return df

        square_rows = df.iloc[:, 1].astype(str).str.strip().eq('Ｓｑｕａｒｅ')
        merchant_names = df.iloc[:, 6].astype('string').str.replace(
            r'^\s*(?:ＳＱ|SQ)\s*[＊*]\s*',
            '',
            regex=True,
        )
        df.loc[square_rows, 'Name'] = merchant_names.loc[square_rows]
        return df

    def make_amounts_negative(self, df):
        # negate the sign on column amount
        df['Amount'] = '-'+df['Amount'].astype(str)
        return df

    def create_unique_id(self, df):
        """Create stable IDs while distinguishing identical statement rows."""
        df['unique_base'] = df['Notes'].replace('', pd.NA).fillna(df['Name'])

        identity = pd.DataFrame({
            'name': df['unique_base'].astype(str),
            'amount': df['Amount'].astype(str),
            'date': df['Date'].astype(str),
        }, index=df.index)
        occurrence = identity.groupby(
            ['name', 'amount', 'date'],
            sort=False,
            dropna=False,
        ).cumcount()

        df['unique_id'] = [
            self.create_hash(json.dumps(
                {
                    'name': name,
                    'amount': amount,
                    'date': date,
                    'occurrence': int(sequence),
                },
                sort_keys=True,
                ensure_ascii=False,
                separators=(',', ':'),
            ))
            for name, amount, date, sequence in zip(
                identity['name'],
                identity['amount'],
                identity['date'],
                occurrence,
            )
        ]
        return df

    def categorize(self, merchant):
        try:
            prompt = f"Merchant Name: {merchant}"
            
            response = model_categorizer.generate_content(prompt)
            
            if not response.text:
                return "Unknown"

            category = response.text.strip().replace('"', '').replace("'", "")
            
            # Validation: fallback to 'Unknown' if Gemini hallucinates a new category
            if category.lower() not in [c.lower() for c in VALID_CATEGORIES]:
                self.logger.warning(f"Invalid category '{category}' for '{merchant}'. Using Unknown.")
                return "Unknown"

            self.logger.info(f'Category: {merchant} -> {category}')
            return category.capitalize()

        except Exception as e:
            self.logger.error(f'Error categorizing {merchant}: {e}')
            return "Unknown"

    def apply_category(self, df):
        """For each row in the df, use the categorize function"""
        df['Category'] = df['Name'].apply(self.categorize)
        return df

def main():
    cc = CreditCardImporter(CC_IMPORTS_DIR)
    cc.run()

if __name__ == '__main__':
    main()
