"""Keep authored multilingual copy intact through the final publish formatter."""
import copy
import json

import pytest

from vstudio import publish as P


@pytest.mark.parametrize('lang,title,body', [
    ('fr', 'Un café', 'Préparer une tasse.'),
    ('ja', 'コーヒー', '一杯を淹れます。'),
    ('ar', 'قهوة', 'تحضير فنجان.'),
    ('pt-BR', 'Café', 'Preparar uma xícara.'),
])
@pytest.mark.parametrize('choice', ['argument', 'platform', 'post', 'content'])
def test_language_block_reaches_final_post(tmp_path, lang, title, body, choice):
    post = {'en': {'title': 'Coffee', 'body': 'An English draft.'},
            lang: {'title': title, 'body': body, 'tags': ['coffee']},
            'use_persona_tags': False}
    kwargs = {'warn': lambda message: pytest.fail(message)}
    if choice == 'argument':
        kwargs['lang'] = lang
    elif choice == 'platform':
        post['lang_by_platform'] = {'instagram': lang}
    elif choice == 'post':
        post['lang'] = lang
    else:
        kwargs['content_lang'] = lang
    path = tmp_path / 'post.json'
    path.write_text(json.dumps(post, ensure_ascii=False), encoding='utf-8')
    post = json.loads(path.read_text(encoding='utf-8'))
    original = copy.deepcopy(post)
    text, selected = P.platform_post(post, 'instagram', **kwargs)
    assert selected['lang'] == lang
    assert selected['title'] == title and selected['body'] == body
    assert title in text and body in text and 'English draft' not in text
    assert post == original


def test_bilingual_remains_en_zh_with_additional_translations():
    post = {'en': {'title': 'Coffee'}, 'zh': {'title': '咖啡'}, 'fr': {'title': 'Café'}}
    selected = P.localize_post(post, 'instagram', bilingual=True)
    assert selected['lang'] == 'en+zh' and selected['title'] == 'Coffee / 咖啡'


def test_bilingual_missing_pair_warns_and_keeps_requested_language():
    warnings = []
    post = {'fr': {'title': 'Café'}, 'ja': {'title': 'コーヒー'},
            'per_platform': {'x': {'title': 'not a language block'}}}
    selected = P.localize_post(post, 'instagram', lang='ja', bilingual=True, warn=warnings.append)
    assert selected['title'] == 'コーヒー' and selected['lang'] == 'ja'
    assert len(warnings) == 1 and 'bilingual' in warnings[0]


def test_missing_translation_warns_without_selecting_metadata():
    warnings = []
    post = {'lang_by_platform': {'title': 'metadata'}, 'fr': {'title': 'Café'}}
    selected = P.localize_post(post, 'instagram', lang='de', warn=warnings.append)
    assert selected['title'] == 'Café' and selected['lang'] == 'fr'
    assert len(warnings) == 1 and "no 'de' copy" in warnings[0]


def test_missing_translation_preserves_legacy_fallback_order():
    warnings = []
    post = {'zh': {'title': '咖啡'}, 'en': {'title': 'Coffee'}, 'fr': {'title': 'Café'}}
    selected = P.localize_post(post, 'instagram', lang='de', warn=warnings.append)
    assert selected['title'] == 'Coffee' and selected['lang'] == 'en'
    assert len(warnings) == 1
