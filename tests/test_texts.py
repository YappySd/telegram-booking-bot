import re
from pathlib import Path

from bot import texts

ROOT = Path(__file__).resolve().parent.parent


def test_every_error_code_has_a_text():
    codes = set()
    for name in ("service.py", "web.py"):
        codes |= set(re.findall(r'(?:error=|_error\()"([a-z_]+)"', (ROOT / "bot" / name).read_text()))
    assert codes, "no error codes found"
    missing = [c for c in codes if c not in texts.ERRORS]
    assert not missing, missing
