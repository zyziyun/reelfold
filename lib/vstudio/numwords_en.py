"""English number words, the subset of ``num2words`` that Kokoro's English G2P (misaki) calls.

The app's runtime ships no ``num2words`` (LGPL-2.1; the bundled set stays permissive). misaki's ``en.py`` imports
``from num2words import num2words`` and calls it for cardinals, ordinals, years and decimals; the desk's bundle step
(apps/desk/scripts/runtime/patch_kokoro.py) points that import here when num2words is not installed. Output matches
num2words' English (``lang="en"``) for those calls, "and" and commas included:

    num2words(123)                  -> "one hundred and twenty-three"
    num2words(21, to="ordinal")     -> "twenty-first"
    num2words(1984, to="year")      -> "nineteen eighty-four"
    num2words(3.14)                 -> "three point one four"
"""
from decimal import Decimal

ONES = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
        "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
SCALES = ("", "thousand", "million", "billion", "trillion", "quadrillion", "quintillion", "sextillion", "septillion",
          "octillion", "nonillion", "decillion")
ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
       "twelve": "twelfth"}


def _below_100(n):
    if n < 20:
        return ONES[n]
    t, o = divmod(n, 10)
    return TENS[t] + (f"-{ONES[o]}" if o else "")


def _below_1000(n):
    h, r = divmod(n, 100)
    if not h:
        return _below_100(r)
    return f"{ONES[h]} hundred" + (f" and {_below_100(r)}" if r else "")


def cardinal(n):
    n = int(n)
    if n < 0:
        return "minus " + cardinal(-n)
    if n < 1000:
        return _below_1000(n)
    groups = []
    while n:
        n, g = divmod(n, 1000)
        groups.append(g)
    if len(groups) > len(SCALES):
        raise OverflowError("number too large")
    parts = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if not g:
            continue
        w = _below_1000(g) + (f" {SCALES[i]}" if i else "")
        # the last group below one hundred joins with "and" ("one thousand and one"), the others with ", "
        if i == 0 and parts and g < 100:
            parts[-1] += f" and {w}"
        else:
            parts.append(w)
    return ", ".join(parts)


def ordinal(n):
    words = cardinal(n)
    head, sep, last = words.rpartition(" ")
    pre, dash, tail = last.rpartition("-")
    if tail in ORD:
        tail = ORD[tail]
    elif tail.endswith("y"):
        tail = tail[:-1] + "ieth"
    else:
        tail += "th"
    return head + sep + pre + dash + tail


def year(n):
    n = int(n)
    if n < 0:
        return year(-n) + " BC"
    hi, lo = divmod(n, 100)
    if hi == 0 or (hi % 10 == 0 and lo < 10) or hi >= 100:
        return cardinal(n)                       # 7, 2000, 2005, 12345
    if lo == 0:
        return f"{cardinal(hi)} hundred"         # 1900
    return f"{cardinal(hi)} " + (f"oh-{ONES[lo]}" if lo < 10 else _below_100(lo))   # 1905, 1984, 2010


def decimal(x):
    if float(x).is_integer():
        return cardinal(int(x))                  # num2words(2.0) -> "two"
    s = format(Decimal(repr(float(x))), "f")
    neg = s.startswith("-")
    whole, _, frac = s.lstrip("-").partition(".")
    out = cardinal(int(whole)) + " point " + " ".join(ONES[int(d)] for d in (frac or "0"))
    return ("minus " if neg else "") + out


def num2words(number, to="cardinal", lang="en"):
    """num2words' English for ``to`` in cardinal / ordinal / year (ints) and decimals (floats)."""
    if lang != "en":
        raise NotImplementedError(f"numwords_en: English only (got lang={lang!r})")
    if to == "ordinal":
        return ordinal(number)
    if to == "year":
        return year(number)
    if to != "cardinal":
        raise NotImplementedError(f"numwords_en: to={to!r}")
    if isinstance(number, float):
        return decimal(number)
    return cardinal(number)
