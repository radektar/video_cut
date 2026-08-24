#!/usr/bin/env python3
"""Stub whisper-cli (D-003): emituje poprawny JSON --output-json-full z tokenami BPE.

Zlicza wywołania w pliku wskazanym przez WHISPER_STUB_COUNT (test cache).
Tekst deterministyczny, rozłożony w czasie trwania wav (ffprobe).
"""
import json
import os
import subprocess
import sys

# zdania z tokenizacją BPE (token bez spacji wiodącej dokleja się do poprzedniego)
SENTENCES = [
    [" To", " jest", " pier", "wsze", " zdanie", " testowe."],
    [" Dru", "gie", " zdanie", " brzmi", " inaczej."],
]


def main() -> int:
    args = sys.argv[1:]
    wav = args[args.index("-f") + 1]
    out_prefix = args[args.index("-of") + 1]

    count_file = os.environ.get("WHISPER_STUB_COUNT")
    if count_file:
        with open(count_file, "a") as f:
            f.write(wav + "\n")

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", wav],
        capture_output=True, text=True, check=True,
    ).stdout.strip())

    usable = max(1.0, dur - 0.4)
    per_sentence = usable / len(SENTENCES)
    transcription = []
    t = 200  # ms
    for sent in SENTENCES:
        sent_end = t + int(per_sentence * 1000) - 300
        n_words = sum(1 for tok in sent if tok.startswith(" "))
        per_word = (sent_end - t) // max(1, n_words)
        tokens = []
        wt = t
        for tok in sent:
            if tok.startswith(" "):
                tokens.append({"text": tok, "offsets": {"from": wt, "to": wt + per_word - 40}})
                wt += per_word
            else:
                tokens.append({"text": tok, "offsets": {"from": tokens[-1]["offsets"]["from"],
                                                        "to": tokens[-1]["offsets"]["to"]}})
        transcription.append({
            "timestamps": {"from": "0", "to": "0"},
            "offsets": {"from": t, "to": sent_end},
            "text": "".join(sent),
            "tokens": tokens,
        })
        t = sent_end + 300

    out = {"result": {"language": "pl"}, "transcription": transcription}
    with open(out_prefix + ".json", "w") as f:
        json.dump(out, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
