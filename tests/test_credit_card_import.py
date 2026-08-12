import dotenv
import pandas as pd

dotenv.load_dotenv = lambda *args, **kwargs: False

from importers.credit_card_import import CreditCardImporter


def test_square_payment_uses_column_seven_and_removes_sq_prefix():
    importer = CreditCardImporter.__new__(CreditCardImporter)
    df = pd.DataFrame(
        [[
            '2026/06/26',
            'Ｓｑｕａｒｅ',
            '2400',
            '１',
            '１',
            '2400',
            'ＳＱ＊（有）ヤードオブエール',
        ]],
        columns=['Date', 'Name', '3', '4', '5', 'Amount', '7'],
    )

    result = importer.handle_square_payments(df)

    assert result.loc[0, 'Name'] == '（有）ヤードオブエール'


def test_non_square_payment_keeps_column_two():
    importer = CreditCardImporter.__new__(CreditCardImporter)
    df = pd.DataFrame(
        [['2026/06/26', 'Merchant', '2400', '１', '１', '2400', 'Other']],
        columns=['Date', 'Name', '3', '4', '5', 'Amount', '7'],
    )

    result = importer.handle_square_payments(df)

    assert result.loc[0, 'Name'] == 'Merchant'


def test_unique_ids_distinguish_identical_transactions():
    importer = CreditCardImporter.__new__(CreditCardImporter)
    transactions = pd.DataFrame([
        {'Date': '2026/08/12', 'Name': 'Coffee Shop', 'Amount': '-500', 'Notes': ''},
        {'Date': '2026/08/12', 'Name': 'Coffee Shop', 'Amount': '-500', 'Notes': ''},
    ])

    result = importer.create_unique_id(transactions)

    assert result['unique_id'].nunique() == 2


def test_unique_ids_use_non_japanese_counterparty_and_are_repeatable():
    importer = CreditCardImporter.__new__(CreditCardImporter)
    transactions = pd.DataFrame([
        {'Date': '2026/08/12', 'Name': 'Coffee Shop A', 'Amount': '-500', 'Notes': ''},
        {'Date': '2026/08/12', 'Name': 'Coffee Shop B', 'Amount': '-500', 'Notes': ''},
    ])

    first_result = importer.create_unique_id(transactions.copy())
    second_result = importer.create_unique_id(transactions.copy())

    assert first_result['unique_id'].nunique() == 2
    assert first_result['unique_id'].tolist() == second_result['unique_id'].tolist()
