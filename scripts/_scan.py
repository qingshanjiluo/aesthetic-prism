"""Report non-ASCII characters in a file, splitting CJK (expected) from anything else
(latin/middle-dot/fullwidth-punct are suspects, they are the usual injection shapes)."""
import io
import sys


def is_cjk(ch):
    o = ord(ch)
    return (
        0x4E00 <= o <= 0x9FFF
        or 0x3400 <= o <= 0x4DBF
        or 0x3000 <= o <= 0x303F
        or 0xFF00 <= o <= 0xFFEF
    )


def main():
    path = sys.argv[1]
    text = io.open(path, encoding="utf-8").read()
    susp = []
    for i in range(len(text)):
        ch = text[i]
        if ord(ch) > 127 and not is_cjk(ch):
            susp.append((i + 1, hex(ord(ch)), ch))
    print("suspicious", len(susp))
    for s in susp[:60]:
        print(s)


if __name__ == "__main__":
    main()
