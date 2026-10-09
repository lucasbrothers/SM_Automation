import pytest
from security.includes import SCAN_SCRIPT


def scanner():
    scope = {}; exec(SCAN_SCRIPT, scope); return scope["scan"]


def test_nested_include_and_unmatched_glob(tmp_path):
    (tmp_path / "main").write_text('Include "child" missing-*.conf\n')
    (tmp_path / "child").write_text("PubkeyAuthentication yes\n")
    scanner()(tmp_path / "main", tmp_path)


def test_match_in_included_file_rejected(tmp_path):
    (tmp_path / "main").write_text("Include child\n")
    (tmp_path / "child").write_text("Match User root\n")
    with pytest.raises(ValueError, match="Match"):
        scanner()(tmp_path / "main", tmp_path)


def test_outside_include_and_cycles_rejected(tmp_path):
    (tmp_path / "main").write_text("Include /outside/*.conf\n")
    with pytest.raises(ValueError, match="stay under"):
        scanner()(tmp_path / "main", tmp_path)
    (tmp_path / "main").write_text("Include main\n")
    with pytest.raises(ValueError, match="cyclic"):
        scanner()(tmp_path / "main", tmp_path)
