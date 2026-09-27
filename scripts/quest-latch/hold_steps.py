"""Turn the air unit's hold log (openipc ab_loop.sh pwr/mark/set -> /tmp/steps_hold.txt) into a step log for
ab_segments.py / ab_link.py.

Input lines "<air epoch> <word> [...] tx=<n> temp=<C>" (ab_loop's `mark X` writes "<epoch> X ..."; a literal
"<epoch> mark X ..." is accepted too):
  - a phase mark (ADAPT1, CTRL, ADAPT2, IDR, ...) sets the current phase; END closes the last step
  - "PWR p<dBm>" (the end of a power change) becomes the step "<PHASE>_p<dBm>"
  - IDR_ON / IDR_OFF become steps of those names
  - PWR_BEGIN, SET_BEGIN and SET are dropped (transitions, not steps)
tx= and temp= are kept, so ab_link.py can still compute the air TX rate per step.

Usage: python3 hold_steps.py steps_hold.txt > steps.txt
"""
import sys

STEP_MARKS = {"IDR_ON", "IDR_OFF"}
TRANSITIONS = {"PWR_BEGIN", "SET_BEGIN", "SET"}


def classify(word, rest, phase):
    """One log line -> (step label or None, new phase)."""
    if word == "END" or word in STEP_MARKS:
        return word, phase
    if word == "PWR" and rest:
        return (f"{phase}_{rest[0]}" if phase else rest[0]), phase
    if word not in TRANSITIONS and "=" not in word and not word[0].isdigit():
        return None, word  # a phase mark: ADAPT1, CTRL, ADAPT2, IDR, ...
    return None, phase


def convert(lines):
    phase, out = "", []
    for line in lines:
        parts = line.split()
        if len(parts) < 2:
            continue
        epoch, word, rest = parts[0], parts[1], parts[2:]
        if word == "mark" and rest:  # tolerate "<epoch> mark <NAME>" as well as ab_loop's "<epoch> <NAME>"
            word, rest = rest[0], rest[1:]
        label, phase = classify(word, rest, phase)
        if label:
            out.append(" ".join([epoch, label] + [p for p in rest if "=" in p]))
    return out


if __name__ == "__main__":
    print("\n".join(convert(open(sys.argv[1], encoding="utf-8"))))
