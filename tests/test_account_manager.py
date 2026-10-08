"""Check remote command boundaries and account identity validation."""
import pytest

from account.manager import account_command, validate_options


@pytest.mark.parametrize("name", ["root;id", "-root", "a\nb", "../sds"])
def test_rejects_invalid_names(name):
    with pytest.raises(ValueError):
        validate_options({"action": "delete", "username": name})


def test_management_identity_protected():
    with pytest.raises(ValueError):
        account_command({"action": "delete", "username": "sds"}, "sds")


def test_create_comment_and_numeric_ids():
    options = validate_options({"action": "create", "username": "example", "sr": "SR123", "full_name": "O'Brien Kim", "uid": "2001"})
    command = account_command(options, "root")
    assert options["comment"].startswith("SR123-")
    assert " -u 2001" in command
    assert "flock -w 30" in command
    assert "O'\"'\"'Brien" in command


def test_delete_keeps_home_and_protects_system_ids():
    command = account_command({"action": "delete", "username": "example"}, "root")
    assert "userdel -- example" in command
    assert "userdel -r" not in command
    assert '-lt 1000' in command


def test_unlock_requires_existing_password():
    command = account_command({"action": "unlock", "username": "example"}, "root")
    assert "Unlock requires a previously set password hash" in command


def test_group_addition_preserves_existing_memberships():
    options = validate_options({"action": "groups", "username": "example", "groups": "users,staff"})
    command = account_command(options, "root")
    assert "getent group users" in command
    assert "usermod -a -G users,staff -- example" in command


def test_group_argument_rejects_injection():
    with pytest.raises(ValueError):
        validate_options({"action": "groups", "username": "example", "groups": "users;id"})


@pytest.mark.parametrize("uid", [True, -1, "1000;id", "999"])
def test_invalid_uid(uid):
    with pytest.raises(ValueError):
        validate_options({"action": "create", "username": "example", "sr": "SR", "full_name": "Name", "uid": uid})
