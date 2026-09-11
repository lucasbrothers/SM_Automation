from common.logger import LogContext
from common.logger import get_logger

context = LogContext(
    hostname="WEB01",
    ip="2001:db8::10",
    os="Linux",
)

logger = get_logger(
    "account",
    context=context,
)

logger.info("Default value test")