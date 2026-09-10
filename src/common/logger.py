import logging

logger = logging.getLogger("SM_Automation")

logger.setLevel(logging.INFO)

console = logging.StreamHandler()

formatter = logging.Formatter(
    "%(asctime)s %(levelname)s %(name)s %(message)s"
)

console.setFormatter(formatter)

logger.addHandler(console)