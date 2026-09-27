"""Turn the air unit's hold log (openipc ab_loop.sh pwr/mark/set -> /tmp/steps_hold.txt) into a step log for
ab_segments.py / ab_link.py.

Input lines "<air epoch> <word> [...] tx=<n> temp=<C>":
  - "mark <PHASE>" (ADAPT1, CTRL, ADAPT2, IDR, ...) sets the current phase; "mark END" closes the last step
  - "PWR p<dBm>" (the end of a power change) becomes the step "<PHASE>_p<dBm>"
  - "mark IDR_ON" / "mark IDR_OFF" become steps "IDR_ON" / "IDR_OFF"
  - PWR_BEGIN, SET_BEGIN, SET and other marks are dropped (transitions, not steps)
tx= and temp= are kept, so ab_link.py can still compute the air TX rate per step.

Usage: python3 hold_steps.py steps_hold.txt > steps.txt
"""
import sys

STEP_MARKS = {"IDR_ON", "IDR_OFF"}


def convert(lines):
    phase, out = "", []
    for line in lines:
        parts = line.split()
        if len(parts) < 2:
            continue
        epoch, word, rest = parts[0], parts[1], parts[2:]
        fields = [p for p in rest if "=" in p]
        if word == "mark" and rest:
            name = rest[0]
            if name == "END":
                out.append(" ".join([epoch, "END"] + fields))
            elif name in STEP_MARKS:
                out.append(" ".join([epoch, name] + fields))
            elif "=" not in name:
                phase = name
        elif word == "PWR" and rest:
            label = f"{phase}_{rest[0]}" if phase else rest[0]
            out.append(" ".join([epoch, label] + fields))
    return out


if __name__ == "__main__":
    print("\n".join(convert(open(sys.argv[1], encoding="utf-8"))))
