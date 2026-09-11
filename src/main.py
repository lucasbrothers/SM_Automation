from common.logger import LoggerManager


manager = LoggerManager()

logger = manager._create_context_logger(
    "account",
    {
        "hostname": "WEB01",
        "ip": "10.10.10.10",
        "os": "Linux",
        "sr_number": "SR-20260911-001",
        "operator": "D25950",
    },
)

logger.info("Account created")

print(f"Logger name: {logger.logger.name}")
print(f"Hostname: {logger.extra['hostname']}")
print(f"IP: {logger.extra['ip']}")
print(f"OS: {logger.extra['os']}")
print(f"SR number: {logger.extra['sr_number']}")
print(f"Operator: {logger.extra['operator']}")