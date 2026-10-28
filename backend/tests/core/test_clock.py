import time

import pytest

from app.core import clock


@pytest.fixture(autouse=True)
def reset_clock():
    yield
    clock.unfreeze()


def test_now_returns_current_epoch_seconds():
    assert abs(clock.now() - time.time()) < 2
    assert isinstance(clock.now(), int)


def test_freeze_and_unfreeze():
    clock.freeze(1_793_102_400)
    assert clock.now() == 1_793_102_400
    clock.unfreeze()
    assert clock.now() != 1_793_102_400
