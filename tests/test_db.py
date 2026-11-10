"""Unit tests for user ID validation."""

import pytest

from pokecal.db import validate_user_id


def test_validate_user_id_accepts_full_snowflake_range():
    assert validate_user_id(" 80351110224678912 ") == "80351110224678912"
    assert validate_user_id("18446744073709551615") == "18446744073709551615"


@pytest.mark.parametrize("bad", ["", "abc", "-1", "0", "1.5", "18446744073709551616", "1e17"])
def test_validate_user_id_rejects_non_snowflakes(bad):
    with pytest.raises(ValueError):
        validate_user_id(bad)
