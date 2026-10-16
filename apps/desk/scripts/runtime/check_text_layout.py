"""Exercise the shipped native paragraph stack, including custom font registration."""
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import ImageFont

from vstudio.textlayout import Layout, Run
from vstudio.textbreak import dictionary_words


def main():
    # Pillow supplies this OFL font. Use a private temporary file so the check
    # covers actual registration without downloading fonts or changing OS fonts.
    with TemporaryDirectory(prefix='reelfold-text-check-') as folder:
        file = Path(folder) / 'selected.ttf'
        file.write_bytes(ImageFont.load_default(size=32).font_bytes)
        font = ImageFont.truetype(str(file), 32)
        with Layout([Run('Reelfold 2026')], font) as layout:
            expected = layout.image()
            assert expected.getbbox(), 'Native paragraph rendered no text'
        with Layout([Run('Reel'), Run('fold 2026')], font) as layout:
            actual = layout.image()
            assert actual.size == expected.size
            assert actual.tobytes() == expected.tobytes(), 'Styled runs changed paragraph shaping'
    text = '🎥การตัดต่อวิดีโอ'
    words = dictionary_words(text)
    assert [text[a:b] for a, b in words.items()] == ['การ', 'ตัด', 'ต่อ', 'วิดีโอ'], 'ICU dictionary data is unavailable'
    print('Pango/Cairo paragraph rendering, selected font registration and ICU dictionary ok')


if __name__ == '__main__':
    main()
