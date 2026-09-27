"""Offline checks of quest_adb.write_prefs (adb is faked). Run: python3 test_quest_adb.py"""
import quest_adb


class FakeAdb:
    """Models the Quest: `exec-in run-as PKG sh -c SCRIPT` runs only the FIRST command of SCRIPT (a "cat > F" writes
    F, anything after "&&" / ";" is lost), `shell run-as PKG mv A B` renames, `shell run-as PKG cat F` reads.
    lose_write: the write never lands. stale_reads: the first N reads still see the old file (a read-back that came
    too early)."""

    def __init__(self, lose_write=False, crlf=False, stale_reads=0):
        self.files = {quest_adb.PREFS_FILE: ""}
        self.lose_write, self.crlf, self.stale_reads = lose_write, crlf, stale_reads
        self.writes, self.moves, self.reads, self.sleeps = [], [], 0, []

    def __call__(self, *a, inp=None):
        if a[0] == "exec-in":
            script = a[-1]
            self.writes.append(script)
            first = script.split("&&")[0].split(";")[0].strip()
            if first.startswith("cat > ") and not self.lose_write:
                self.files[first[len("cat > "):].strip()] = inp.decode() if inp else ""
            return ""
        cmd = a[3:]  # after "shell", "run-as", PKG
        if cmd[0] == "mv":
            self.moves.append(cmd[1:])
            if cmd[1] in self.files:
                self.files[cmd[2]] = self.files.pop(cmd[1])
            return ""
        self.reads += 1
        out = "" if self.reads <= self.stale_reads else self.files.get(cmd[1], "")
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


def test_write_goes_to_a_tmp_file_then_a_separate_rename():
    fake = FakeAdb()
    with_fake(fake, lambda: quest_adb.write_prefs(XML))
    assert fake.writes == ["cat > " + quest_adb.PREFS_TMP]
    assert fake.moves == [(quest_adb.PREFS_TMP, quest_adb.PREFS_FILE)]
    assert fake.files == {quest_adb.PREFS_FILE: XML}


def test_a_rename_chained_inside_exec_in_would_be_caught():
    """The 18:16-22:34 failure: with "cat > tmp && mv tmp final" in one exec-in, only the tmp file changes."""
    fake = FakeAdb()
    fake("exec-in", "run-as", "pkg", "sh", "-c", "cat > %s && mv %s %s" % (
        quest_adb.PREFS_TMP, quest_adb.PREFS_TMP, quest_adb.PREFS_FILE), inp=XML.encode())
    assert fake.files[quest_adb.PREFS_FILE] == "" and fake.files[quest_adb.PREFS_TMP] == XML


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
