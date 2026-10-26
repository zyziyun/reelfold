"""One caption line-breaker for every script (vstudio.subs.caption_chunks / balanced_wrap / split_two / join_caption):
English never splits inside a word ("anywa / y", "Every index mak / es writes slower" in the English demo batch),
CJK splits by character with no line starting on closing punctuation, mixed text keeps latin runs whole."""
import re
import sys
from pathlib import Path

import pytest

from vstudio import draw
from vstudio import subs as S
from vstudio.batch import lfsplit as LS

ROOT = Path(__file__).resolve().parents[1]

EN = ("I think that's the interviewer question for anyway, if you query the user anyway on every request "
      "then why are you using a JWT at all instead of a session cookie with Redis behind it")
ZH = "我们用这个模型做了一个非常长的测试，然后把结果发到了小红书上面，大家觉得效果怎么样呢？我觉得还挺好的。"
MIX = "今天我们用Claude Code和HyperFrames做了一个讲解视频，整个流程只用了十分钟，而且export也很快"


def test_thai_caption_chunks_use_dictionary_words_without_inserting_spaces():
    text = 'การตัดต่อวิดีโอช่วยให้ผู้สร้างสามารถเล่าเรื่องราวที่น่าสนใจและแบ่งปันความรู้กับผู้ชมได้อย่างชัดเจน'
    for width in (8, 12, 20):
        chunks = S.caption_chunks(text, width, max_lines=2)
        assert len(chunks) > 1
        assert S.join_caption(chunks) == text
        assert any('วิดีโอ' in chunk for chunk in chunks)
        assert any('เรื่องราว' in chunk for chunk in chunks)


def _words(s):
    return re.findall(r"[A-Za-z0-9'’]+", s)


def test_english_chunks_never_split_a_word():
    for width in (6, 9, 12, 16, 22, 30):
        chunks = S.caption_chunks(EN, width, max_lines=2)
        assert len(chunks) > 1 or S.text_width(EN) <= 2 * width
        assert S.join_caption(chunks) == EN                      # nothing lost, spaces kept at the seams
        for c in chunks:
            assert all(w in _words(EN) for w in _words(c)), (width, c)
            assert "anywa" not in c.replace("anyway", "")
            assert not c.startswith((",", ".", "?"))


def test_chinese_chunks_by_character_with_no_break_punctuation():
    for width in (5, 8, 10, 14):
        chunks = S.caption_chunks(ZH, width, max_lines=2)
        assert "".join(chunks) == ZH
        for c in chunks:
            for ln in S.balanced_wrap(c, width):
                assert ln[0] not in "，。、！？；：”’）》」』】,.!?;:)"
                assert S.text_width(ln) <= width + 1                  # a glued closing mark may hang


def test_mixed_text_keeps_latin_runs_whole():
    for width in (6, 8, 10, 12):
        lines = S.balanced_wrap(MIX, width)
        assert S.join_caption(lines).replace(" ", "") == MIX.replace(" ", "")
        flat = " ".join(lines)
        for w in ("Claude", "HyperFrames", "export"):
            assert w in flat, (width, lines)
        chunks = S.caption_chunks(MIX, width, max_lines=2)
        assert "Claude Code" in S.join_caption(chunks)


def test_accented_and_long_words_stay_whole():
    assert S.split_two("café crème brûlée au chocolat") == ["café crème brûlée", "au chocolat"]
    assert S.caption_chunks("Supercalifragilisticexpialidocious", 4) == ["Supercalifragilisticexpialidocious"]
    f = draw.load_font("cjk-bold", 80)
    assert draw.wrap("Authentication everywhere", f, 200) == ["Authentication", "everywhere"]   # overflow, no "Authenticati / on"
    assert not draw.fits(["Authentication"], f, 200)


def test_join_caption_seams():
    assert S.join_caption(["any", "way"]) == "any way"
    assert S.join_caption([" anyway", "so we ", "", "start."]) == "anyway so we start."
    assert S.join_caption(["我们用", "Claude Code", "做了视频"]) == "我们用Claude Code做了视频"
    assert S.join_caption(["Claude", "Code做了"]) == "Claude Code做了"
    assert S.join_caption(["hello", ", world"]) == "hello, world"
    assert S.join_caption(['3', '.', '5']) == '3.5'
    assert S.join_caption(['1,', '000']) == '1,000'
    assert S.join_caption(['well-', 'known']) == 'well-known'
    assert S.join_caption(['안녕하세요', '여러분']) == '안녕하세요 여러분'


def test_asr_cues_share_unicode_spacing_and_numeric_seams():
    for parts, expected in [(['مرحبا', 'بالعالم.'], 'مرحبا بالعالم.'),
                            (['Привет', 'мир.'], 'Привет мир.'),
                            (['안녕하세요', '여러분.'], '안녕하세요 여러분.'),
                            (['value', '3', '.', '5', 'and', '1,', '000'], 'value 3.5 and 1,000'),
                            (['你好', '世界。'], '你好世界。')]:
        words = [dict(w=w, t=i*.4, te=(i+1)*.4) for i, w in enumerate(parts)]
        assert S.join_caption(c.text for c in S.cues_from_words(words, fixes=False)) == expected


@pytest.mark.parametrize('text', [
    'احتفظ بصوتك وراجع الترجمة قبل النشر.',
    'Проверьте субтитры перед публикацией.',
    'यह पहला वीडियो है।',
    'בדקו את הכתוביות לפני הפרסום.',
    'Αυτό είναι το πρώτο βίντεο.',
    'cafe\u0301 cre\u0300me avant publication.',
    'ﺍﺣﺘﻔﻆ ﺑﺼﻮﺗﻚ',
    '안녕하세요 여러분 다시 만나요.',
    '다시 만나요 네',
])
def test_wrapping_keeps_unicode_words_and_combining_marks(text):
    # Even a word wider than the box stays whole: the caller can shrink its font, never split a name.
    expected = text.split()
    for width in (2, 5, 8):
        lines = S.balanced_wrap(text, width)
        assert [w for line in lines for w in line.split()] == expected
        chunks = S.caption_chunks(text, width, max_lines=2)
        assert S.join_caption(chunks) == text
    f = draw.load_font('cjk-bold', 48)
    for width in (90, 240, 400):
        lines = draw.wrap(text, f, width, balance=True)
        assert [w for line in lines for w in line.split()] == expected


@pytest.mark.parametrize('word', ['Authentication', 'احتفظ', 'वीडियो', 'публикацией'])
def test_highlight_does_not_split_a_long_word(word):
    f = draw.load_font('cjk-bold', 48)
    text = f'【{word}】'
    assert draw.wrap(text, f, 10) == [text]
    assert S.balanced_wrap(text, 1) == [text]


def test_ass_rtl_uses_libass_whole_line_layout_and_preserves_logical_text(tmp_path):
    text = 'راجع 【الترجمة】 قبل النشر.'
    out = tmp_path / 'rtl.ass'
    S.ass_write(iter([S.Cue(0, 2, text)]), str(out), font_name='Arial',
                extra_styles=[dict(name='Note')],
                extra_events=iter([dict(start=0, end=2, text='A note', style='Note')]))
    content = out.read_text()
    assert all(line.endswith(',-1') for line in content.splitlines() if line.startswith('Style:'))
    assert 'راجع ' in content and 'الترجمة' in content and ' قبل النشر.' in content
    assert content.count('Dialogue:') == 2


def test_ass_ltr_keeps_legacy_encoding_and_rtl_can_explicitly_request_it(tmp_path):
    for text, encoding in [('Hello 世界.', None), ('בדקו כתוביות.', 1)]:
        out = tmp_path / 'compatible.ass'
        S.ass_write([S.Cue(0, 2, text)], str(out), encoding=encoding, font_name='Arial')
        assert all(line.endswith(',1') for line in out.read_text().splitlines() if line.startswith('Style:'))


def test_ass_alt_or_extra_rtl_text_also_selects_whole_line_layout(tmp_path):
    out = tmp_path / 'alternate.ass'
    for alt, extra in [('مرحبا.', []), ('', [(0, 2, 'שלום.', 'Sub')])]:
        S.ass_write([S.Cue(0, 2, 'Hello.', alt=alt)], str(out), extra_events=extra, font_name='Arial')
        assert next(line for line in out.read_text().splitlines() if line.startswith('Style: Sub')).endswith(',-1')


def test_cover_title_uses_the_shared_breaker():
    assert LS._title_parts("Every index makes writes slower") == ("Every index makes", "writes slower")
    assert LS._title_parts("JWT payloads are encoded not encrypted") == ("JWT payloads are", "encoded not encrypted")
    assert LS._title_parts("一行代码搞定Postgres全文搜索") == ("一行代码搞定", "Postgres全文搜索")
    assert LS._title_parts("If you query the user anyway, why JWT?") == ("If you query the user anyway", "why JWT?")
    for t in ("Ask AI to fix a slow query then verify with EXPLAIN", "The honest interview answer about MySQL 8"):
        a, b = LS._title_parts(t)
        assert f"{a} {b}" == t and all(w in t.split() for w in (a + " " + b).split())


def test_spoken_hook_lines_join_english_with_spaces():
    tl = [dict(kind="clip", hook=True, final_t0=0.0, t0=0.0, t1=4.0, speed=1.0)]
    cues = [dict(start=0.0, end=2.0, text="Every index you add"), dict(start=2.0, end=4.0, text="makes writes slower")]
    out = LS.spoken_hook_lines(tl, cues)
    assert out[0] == ["Every index you add", "makes writes slower"]
    tl[0].pop("hook_lines")
    one = [dict(start=0.0, end=4.0, text="Every index you add makes writes slower")]
    assert LS.spoken_hook_lines(tl, one)[0] == ["Every index you add", "makes writes slower"]


def _vertical():
    d = str(ROOT / "workflows" / "longform-to-short" / "scripts")
    sys.path.insert(0, d)
    try:
        import _vertical as V
        return V
    finally:
        sys.path.remove(d)


def test_vertical_relayout_splits_english_on_words_only():
    from vstudio import platform as PF
    V = _vertical()
    prof = PF.parse_targets(["tiktok"])[0]
    cue = S.Cue(0.0, 9.0, EN)
    out = V.relayout_cues([cue], prof)
    assert len(out) > 1
    assert S.join_caption([c.text for c in out]) == EN
    for c in out:
        assert all(w in _words(EN) for w in _words(c.text)), c.text
        assert len(c.text) <= 2 * prof.caption["max_chars_en"] + 2
    assert abs(out[-1].end - 9.0) < 1e-6


@pytest.mark.parametrize("scale", [16, 36, 72])
def test_pixel_wrapping_keeps_semantic_preferences_at_large_font_sizes(monkeypatch, scale):
    text = "即使网络断开，我依然能继续编辑草稿"
    monkeypatch.setattr(S, "_word_bounds", lambda _: {2, 4, 6, 7, 8, 10, 11, 13, 15, 17})
    expected = S.balanced_wrap(text, 8)
    actual = S.balanced_wrap(text, 8 * scale, measure=lambda value: S.text_width(value) * scale)
    assert actual == expected
    assert any("断开" in line for line in actual)
    assert any("依然" in line for line in actual)
    assert any("继续" in line for line in actual)


@pytest.mark.parametrize("text", [
    "이 영상에서는 화면을 공유하면서 설명하는 방법을 보여드립니다",
    "このどうがではがめんをきょうゆうしながらせつめいします",
    "هذا الفيديو يشرح كيفية مشاركة الشاشة أثناء تسجيل الدرس",
    "Это видео объясняет как записывать экран во время урока",
    "इस वीडियो में स्क्रीन रिकॉर्ड करने का तरीका बताया गया है",
])
def test_reading_time_counts_non_latin_speech(text):
    assert S.reading_time(text, lo=0, hi=float("inf")) > 2.5


def test_reading_time_reuses_dictionary_and_markup_boundaries():
    thai = "การตัดต่อวิดีโอช่วยให้ผู้สร้างสามารถเล่าเรื่องราวที่น่าสนใจ"
    assert S.reading_time(thai, lo=0, hi=float("inf")) > 2.5
    assert S.reading_time("**café** déjà vu", lo=0) == S.reading_time("café déjà vu", lo=0)
    assert S.reading_time("编辑 draft", lo=0) == round(1 + 2/6 + 1/3.5, 2)
    assert S.reading_time("你好世界", lo=0) == round(1 + 4/6, 2)
    assert S.reading_time("ＡＢＣ ｄｒａｆｔ", lo=0) == S.reading_time("ABC draft", lo=0)


def test_question_card_reading_time_keeps_bounds_and_shared_estimate():
    from vstudio.qa import reading_time
    assert reading_time("Hi") == 2.5
    assert reading_time("word " * 100) == 6
    assert reading_time("word " * 100, hi=float("inf")) > 6
    assert reading_time("이 영상에서는 화면을 공유합니다", hi=100) == S.reading_time("이 영상에서는 화면을 공유합니다", hi=100)
