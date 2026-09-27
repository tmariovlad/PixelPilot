"""Offline checks of quest_adb.write_prefs (adb is faked). Run: python3 test_quest_adb.py"""
import quest_adb


class FakeAdb:
    """lose_write: the write never lands. stale_reads: the first N reads still see the old file (a read-back that
    came too early)."""

    def __init__(self, lose_write=False, crlf=False, stale_reads=0):
        self.file, self.lose_write, self.crlf, self.stale_reads = "", lose_write, crlf, stale_reads
        self.new, self.writes, self.reads, self.sleeps = "", [], 0, []

    def __call__(self, *a, inp=None):
        if a[0] == "exec-in":
            self.writes.append(a[-1])
            if not self.lose_write:
                self.new = inp.decode()
            return ""
        self.reads += 1
        out = self.file if self.reads <= self.stale_reads or self.lose_write else self.new
        return out.replace("\n", "\r\n") if self.crlf else out


def with_fake(fake, fn):
    real_adb, real_sleep = quest_adb.adb, quest_adb._sleep
    quest_adb.adb, quest_adb._sleep = fake, fake.sleeps.append
    try:
        return fn()
    finally:
        quest_adb.adb, quest_adb._sleep = real_adb, real_sleep


XML = quest_adb.PREFS_HEADER + '    <boolean name="od_enabled" value="false" />\n</map>\n'


def raises(fake):
    try:
        with_fake(fake, lambda: quest_adb.write_prefs(XML))
    except RuntimeError:
        return True
    return False


def test_write_that_lands_passes():
    fake = FakeAdb()
    with_fake(fake, lambda: quest_adb.write_prefs(XML))
    assert fake.reads == 1 and fake.sleeps == []


def test_write_is_atomic_tmp_then_mv():
    fake = FakeAdb()
    with_fake(fake, lambda: quest_adb.write_prefs(XML))
    cmd, = fake.writes
    assert cmd.startswith("cat > shared_prefs/general.xml.tmp && mv shared_prefs/general.xml.tmp "), cmd
    assert cmd.endswith(" shared_prefs/general.xml"), cmd


def test_crlf_read_back_still_matches():
    with_fake(FakeAdb(crlf=True), lambda: quest_adb.write_prefs(XML))


def test_first_read_differs_second_ok():
    fake = FakeAdb(stale_reads=1)
    assert not raises(fake)
    assert fake.reads == 2 and fake.sleeps == [quest_adb.READBACK_WAIT_S]


def test_late_but_within_retries_passes():
    fake = FakeAdb(stale_reads=quest_adb.READBACK_TRIES - 1)
    assert not raises(fake)
    assert fake.reads == quest_adb.READBACK_TRIES


def test_stale_on_every_read_raises():
    fake = FakeAdb(stale_reads=quest_adb.READBACK_TRIES)
    assert raises(fake)
    assert fake.reads == quest_adb.READBACK_TRIES
    assert len(fake.sleeps) == quest_adb.READBACK_TRIES - 1     # no pointless sleep after the last read


def test_lost_write_raises():
    assert raises(FakeAdb(lose_write=True))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
