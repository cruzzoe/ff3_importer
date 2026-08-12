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
