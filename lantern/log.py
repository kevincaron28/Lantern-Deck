"""Local rotating log. Tokens and pairing secrets are redacted before writing."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re

PATTERNS = [
    (re.compile(r'(admin=|Bearer\s+|token["\']?\s*[:=]\s*["\']?)[^\s&"\',}]+', re.I), r'\1[redacted]'),
    (re.compile(r'\b[0-9a-f]{32,}\b', re.I), '[redacted]'),
    (re.compile(r'\b[A-Za-z0-9_-]{40,}\b'), '[redacted]'),
]


def redact(text):
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def setup(directory, level=logging.INFO):
    """Log to <data>/logs/lantern.log (1 MB x 3). Returns the log folder."""
    folder = Path(directory) / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / 'lantern.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.setLevel(level)
    for existing in list(root.handlers):
        if isinstance(existing, RotatingFileHandler):
            root.removeHandler(existing)
    root.addHandler(handler)
    return folder
