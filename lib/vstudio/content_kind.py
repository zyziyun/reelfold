"""Editorial purpose is separate from the recipe used to execute it.

A commercial made from real photos must not become a generated ad; recorded
comedy must not lose its performance to an automatic speech speed-up.
"""
import re

PATTERNS = {
    "product": r"电商|带货|商品展示|产品演示|商品演示|产品广告|产品短片|e-?commerce|shopping ad|\bproduct[- ](?:design[- ])?(?:ad\b|commercial|spot\b|showcase|demonstration\b|demo\b|video|film)",
    "company": r"企业宣传|公司宣传|品牌形象片|工业(?:流程|生产)?(?:短片|视频|宣传片)|生产流程(?:短片|视频)|\b(?:industrial|manufacturing)(?:[- ]process)?[- ](?:film|video)\b|\b(?:corporate|company)(?:[- ]brand)?[- ](?:film|video|introduction|intro|profile|promo(?:tion)?)\b|\benterprise[- ](?:introduction|intro|profile|promo(?:tion)?)\b|brand film",
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
            "Company film, not a product UI tour or travel montage. Follow the brief: a brand introduction needs "
            "an audience-facing question, supplied identity/promise, supported services and a clear CTA; "
            "a process study needs action and result. Do not turn every company brief into a machine-label sequence. "
            "When authentic coverage exists, establish the real place and team, "
            "show their process, then its visible result and one supplied contact/CTA. Tie each claim to supplied "
            "materials; never invent customers, certifications, rankings, impact figures or a client logo. "
            "Use a coherent visual identity and deliberate wide-to-detail progression. Give identity, service "
            "explanation and CTA distinct hierarchy using supported composition, emphasis and reading time. "
            "Use role/process labels for actual explanations, not as the only treatment of every message. "
            "Evaluate picture occupancy at phone size: a short caption should not force landscape footage "
            "into a small inset with a large empty band. Preserve meaningful action when reframing. "
            "Preserve real people and equipment; do not imply stock or generated pictures are this company. "
            "A process verb needs a visible action, not just nearby equipment or an out-of-focus worker. "
            "Keep the interaction and its result readable in each requested crop. If the supplied footage "
            "does not show the action, use a supported descriptive label. Disclose missing process coverage "
            "and verification limits in EDITORIAL_NOTES for the creator, not as production diagnostics in "
            "the film's captions or narration. Keep viewer-facing copy factual and self-contained: for example, "
            "'Cans on the line', not 'Finished output unverified'. Retain necessary stock/illustration disclosures "
            "and any caveat the viewer needs to avoid a misleading claim; never hide uncertainty by presenting "
            "an unsupported claim as fact. Follow an explicit request for an on-screen limitation."
        ),
        "sketch": (
            "Comedy performance: preserve setup, escalation, payoff and the reaction beat. A pause may be the joke; "
            "do not uniformly speed up or remove intentional repetition. Preserve the original voices and shot "
            "continuity. Do not replace a recorded performance with AI generation unless explicitly requested."
        ),
    }.get(kind, "")
