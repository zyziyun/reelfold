"""Editorial purpose is separate from the recipe used to execute it.

A commercial made from real photos must not become a generated ad; recorded
comedy must not lose its performance to an automatic speech speed-up.
"""
import re

PATTERNS = {
    "product": r"电商|带货|商品展示|产品演示|商品演示|产品广告|产品短片|e-?commerce|shopping ad|\bproduct[- ](?:design[- ])?(?:ad\b|commercial|spot\b|showcase|demonstration\b|demo\b|video|film)",
    "company": r"企业宣传|公司宣传|品牌形象片|corporate (?:brand )?(?:film|video)|company (?:brand )?(?:film|video)|brand film",
    "sketch": r"段子|小品|情景喜剧|搞笑(?:短片|短剧|段子)|comedy(?:\s+(?:sketch|skit|film|video))?|\bskit\b|\bsketch\b",
}


# Negation belongs to the requested format, including its article/classifier.
# Do not negate “not only / 不只是”, or carry a negative across a new clause.
_NEGATED = re.compile(
    r"(?:\b(?:no|not|without|never|avoid|skip)|\b(?:do not|don't)\s+(?:make|create|use))"
    r"\s+(?:(?:a|an|the|any|another|new|generic|typical|standard|traditional)\s+)*$|"
    r"(?:不要|别|不需要|不用|不是|不做)(?:做成|制作|做|用)?"
    r"(?:(?:一个|一条|一部|这种|那种|普通|传统|常见|的)\s*)*$", re.I)


def detect(text):
    text = str(text or "").lower()
    for kind, pattern in PATTERNS.items():
        for hit in re.finditer(pattern, text, re.I):
            before = text[:hit.start()]
            if not _NEGATED.search(before):
                return kind
    return None


def direction(kind):
    return {
        "product": (
            "Product film, not a travel essay. Open on the actual product in use; show one visible feature "
            "and its supporting close-up or demonstration, then return to a clear product hero and one CTA. "
            "Preserve the real product's colour, proportions, labels and branding. Only state attributes supplied "
            "in the brief or visible in the sources. Do not invent price, discount, sales, testimonials or performance. "
            "Music-mode cues are concise feature labels tied to the current picture, not poetic scenery lines. "
            "Keep any requested language and identity. Use purposeful cuts and restrained detail moves."
        ),
        "company": (
            "Company film, not a product UI tour or travel montage. Establish the real place and team, "
            "show their process, then its visible result and one supplied contact/CTA. Tie each claim to supplied "
            "materials; never invent customers, certifications, rankings, impact figures or a client logo. "
            "Use a coherent visual identity, clear role/process labels and deliberate wide-to-detail progression. "
            "Preserve real people and equipment; do not imply stock or generated pictures are this company. "
            "A process verb needs a visible action, not just nearby equipment or an out-of-focus worker. "
            "Keep the interaction and its result readable in each requested crop. If the supplied footage "
            "does not show the action, use a supported descriptive label and disclose the missing process coverage."
        ),
        "sketch": (
            "Comedy performance: preserve setup, escalation, payoff and the reaction beat. A pause may be the joke; "
            "do not uniformly speed up or remove intentional repetition. Preserve the original voices and shot "
            "continuity. Do not replace a recorded performance with AI generation unless explicitly requested."
        ),
    }.get(kind, "")
