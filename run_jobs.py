import logging
import os

from bank_import import BankImporter
from credit_card_import import CreditCardImporter
from restaurant_import import RestaurantCardImporter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CC_IMPORTS_DIR=os.getenv("CC_IMPORTS_DIR")
BANK_IMPORTS_DIR=os.getenv("BANK_IMPORTS_DIR")
RESTAURANT_IMPORTS_DIR=os.getenv("RESTAURANT_IMPORTS_DIR")

def main():
    logging.info('Running all jobs...')
    BankImporter(BANK_IMPORTS_DIR).run()
    CreditCardImporter(CC_IMPORTS_DIR).run()
    RestaurantCardImporter(RESTAURANT_IMPORTS_DIR).run() 
    logging.info('All jobs complete.')


if __name__ == "__main__":
    main()  