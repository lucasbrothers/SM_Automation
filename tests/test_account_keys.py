import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from account.keys import validate_public_key
from account.manager import validate_options


def test_real_public_key_is_normalized_without_comment():
    key = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode()
    options = validate_options({"action": "public_key", "username": "example", "public_key": key + " operator@host"})
    assert options["public_key"] == key


@pytest.mark.parametrize("value", ["ssh-ed25519 invalid", "-----BEGIN OPENSSH PRIVATE KEY-----", "ssh-ed25519 AAAA\nssh-rsa AAAA", 'command="id" ssh-ed25519 AAAA', None])
def test_invalid_or_private_keys_and_options_are_rejected(value):
    with pytest.raises(ValueError):
        validate_public_key(value)
