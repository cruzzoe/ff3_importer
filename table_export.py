import os
import re
import unicodedata

import pandas as pd
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))



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
    print(f'Translate: {text} to {translated_text}')
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
    print(f'Selected merchant: {merchant} to {category}')
    return category.capitalize()

def apply_category(df):
    """For each row in the df, use the categorize function to select an appropriate category for the merchant based on column Name"""
    df['Category'] = df['Name'].apply(categorize)
    return df

def apply_normalization(df):
    df['Name'] = df['Name'].apply(normalize_text)
    return df

def main():
    with open('table_export.html', 'r') as f:
        content = f.read()
    df = html_to_df(content)
    df = remove_non_transactions(df)
    df = handle_square_payments(df)
    df = make_amounts_negative(df)
    df = handle_pure_japanese(df)
    df = apply_category(df) 
    df = apply_normalization(df)
    df.to_csv('pandas_parsed.csv')

if __name__ == '__main__':
    main()