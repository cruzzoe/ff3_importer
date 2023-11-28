import logging
import os
import argparse

from importers.bank_import import BankImporter
# from credit_card_import import CreditCardImporter
from importers.restaurant_import import RestaurantCardImporter
from importers.gc_bank_importer import GoCardlessBankImporter
from importers.gc_cc_1_import import GoCardlessCC1Importer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CC_IMPORTS_DIR=os.getenv("CC_IMPORTS_DIR")
BANK_IMPORTS_DIR=os.getenv("BANK_IMPORTS_DIR")
RESTAURANT_IMPORTS_DIR=os.getenv("RESTAURANT_IMPORTS_DIR")
GC_IMPORTS_DIR=os.getenv("GC_IMPORTS_DIR")
GC_CC1_IMPORTS_DIR=os.getenv("GC_CC1_IMPORTS_DIR")
GC_BANK1_IMPORTS_DIR=os.getenv("GC_BANK1_IMPORTS_DIR")


def run(mode):
    if mode == 'monthly':
        # run monthly
        logging.info('Running SCRAPING bank job...')
        BankImporter(BANK_IMPORTS_DIR).run()
        RestaurantCardImporter(RESTAURANT_IMPORTS_DIR).run()
        logging.info('Bank job complete.')

    elif mode == 'daily':
        # run GC jobs daily
        logging.info('Running GC job...')
        GoCardlessBankImporter(GC_BANK1_IMPORTS_DIR).run()
        GoCardlessCC1Importer(GC_CC1_IMPORTS_DIR).run()   
        logging.info('Credit card job complete.')

    # logging.info('Running all jobs...')
    # BankImporter(BANK_IMPORTS_DIR).run()
    # CreditCardImporter(CC_IMPORTS_DIR).run()
    # RestaurantCardImporter(RESTAURANT_IMPORTS_DIR).run() 
    # logging.info('All jobs complete.')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run all jobs.')
    parser.add_argument('--mode', type=str)
    args = parser.parse_args()
    mode = args.mode
    run(mode)  