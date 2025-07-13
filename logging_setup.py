# logging_setup.py
import logging
import logging.handlers
import sys

def setup_logging():
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter('%(asctime)s - %(levelname)-8s - %(filename)-15s:%(lineno)d - %(message)s')
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Optional: Colored logs for the console
    try:
        import coloredlogs
        coloredlogs.install(level='INFO', logger=log, fmt='%(asctime)s - %(levelname)-8s - %(filename)-15s:%(lineno)d - %(message)s')
    except ImportError:
        log.addHandler(console_handler)
        
    # File handler
    file_handler = logging.handlers.RotatingFileHandler(
        filename='bot_activity.log', 
        encoding='utf-8', 
        maxBytes=5 * 1024 * 1024, # 5 MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    log.addHandler(file_handler)
    log.info("================== BOT STARTING UP ==================")