import uuid

import pytest
from jkr_db.session import _validated_uuid_literal


def test_accepts_uuid_object():
    value = uuid.uuid4()
    assert _validated_uuid_literal(value) == str(value)


def test_accepts_canonical_uuid_string():
    value = "10000000-0000-0000-0000-000000000001"
    assert _validated_uuid_literal(value) == value


def test_rejects_sql_injection_attempt():
    with pytest.raises(ValueError):
        _validated_uuid_literal("x'; DROP TABLE workspaces; --")


def test_rejects_empty_string():
    with pytest.raises(ValueError):
        _validated_uuid_literal("")
