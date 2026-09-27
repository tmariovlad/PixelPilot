"""Offline checks of quest_adb.write_prefs (adb is faked). Run: python3 test_quest_adb.py"""
import quest_adb


class FakeAdb:
    def __init__(self, lose_write=False, crlf=False):
        self.file, self.lose_write, self.crlf = "", lose_write, crlf

    def __call__(self, *a, inp=None):
        if a[0] == "exec-in":
            if not self.lose_write:
                self.file = inp.decode()
            return ""
        out = self.file
        return out.replace("\n", "\r\n") if self.crlf else out


def with_fake(fake, fn):
    real = quest_adb.adb
    quest_adb.adb = fake
    try:
        return fn()
    finally:
        quest_adb.adb = real


XML = quest_adb.PREFS_HEADER + '    <boolean name="od_enabled" value="false" />\n</map>\n'


def test_write_that_lands_passes():
    with_fake(FakeAdb(), lambda: quest_adb.write_prefs(XML))


def test_crlf_read_back_still_matches():
    with_fake(FakeAdb(crlf=True), lambda: quest_adb.write_prefs(XML))


def test_lost_write_raises():
    try:
        with_fake(FakeAdb(lose_write=True), lambda: quest_adb.write_prefs(XML))
    except RuntimeError:
        return
    raise AssertionError("a lost write must raise")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
