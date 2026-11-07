"""Purpose routing respects exclusions without discarding an affirmative brief."""
import pytest

from vstudio.content_kind import detect


@pytest.mark.parametrize("prompt,expected", [
    ("Not a comedy sketch; keep this interview natural.", None),
    ("Make this a company film, not a product ad.", "company"),
    ("不要做成一个搞笑段子，保留访谈原声", None),
    ("不是一条普通的产品广告，做企业宣传片", "company"),
    ("Don't make a product ad. Edit my talking-head recording.", None),
    ("Avoid a generic corporate film; make a product showcase.", "product"),
    ("Not only a product ad, also show its packaging.", "product"),
    ("不只是一个搞笑段子，还要有温暖的结尾", "sketch"),
    ("Do not change the timing of this comedy sketch", "sketch"),
    ("不要加速这个搞笑段子", "sketch"),
    ("No voice-over. Make a corporate film.", "company"),
    ("Create a cinematic product ad", "product"),
    ("Create a product design film from these illustrations", "product"),
    ("Make a product-design video", "product"),
    ("Not a product design film; make a company film", "company"),
    ("Discuss product design in this interview", None),
    ("Create a product demonstration edit", "product"),
    ("Create a product-demo", "product"),
    ("制作产品演示短片", "product"),
    ("Not a product demo; make a company film", "company"),
    ("Discuss product demographics", None),
    ("Create an 18-second portrait industrial process film", "company"),
    ("Make a manufacturing video from the supplied footage", "company"),
    ("An industrial-process film showing equipment", "company"),
    ("制作工业流程短片，保留真实设备", "company"),
    ("剪一个生产流程视频", "company"),
    ("Not an industrial process film; keep the interview", None),
    ("不要制作工业流程短片，保留采访", None),
    ("Discuss industrial processes in this interview", None),
    ("Explain manufacturing in this lecture", None),
    ("Create an 18-second enterprise company introduction from stock clips", "company"),
    ("Make a company-profile video", "company"),
    ("Create a corporate intro", "company"),
    ("Make an enterprise promo", "company"),
    ("Create a company promotion", "company"),
    ("Not a company introduction; retain the interview", None),
    ("Avoid a generic enterprise promo; use my original speech", None),
    ("Discuss enterprise software in this lecture", None),
    ("Explain company profitability", None),
    ("Discuss corporate videography careers", None),
])
def test_purpose_negation(prompt, expected):
    assert detect(prompt) == expected
