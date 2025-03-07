import logging

class LoggingService:
    def __init__(self):
        logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

    def log_candidates(self, candidates):
        for idx, candidate in enumerate(candidates, start=1):
            self.logger.info(f"Aday {idx}: {candidate}")
