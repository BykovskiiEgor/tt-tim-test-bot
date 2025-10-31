import logging

logging.basicConfig(
    filename='bot.log',
    filemode='a', 
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)