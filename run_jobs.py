from bank_export import BankImporter 
from credit_card_import import CreditCardImporter
from restaurant_import import RestaurantCardImporter
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    # TODO fix initialization of Importer instances
    logging.info('Running all jobs...')
    BankImporter().run()
    CreditCardImporter().run()
    RestaurantCardImporter().run() 
    logging.info('All jobs complete.')