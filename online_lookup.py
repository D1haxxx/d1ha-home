"""Live encyclopedia lookup. Uses source text, never the GPT to invent facts."""
from functools import lru_cache
from difflib import get_close_matches
import re
import time
from urllib.parse import quote, urlencode
import httpx
from safety import request_filter

HEADERS = {'User-Agent': 'D1ha/1.1 (https://www.mediawiki.org/wiki/API:Main_page; educational local bot)'}


def short_answer(text):
    # Simple English Wikipedia is already written in easier English.
    # Shorten its opening; do not pretend this is neural paraphrasing.
    text = re.sub(r'\[[^\]]*\]', '', text)
    while re.search(r'\([^()]*\)', text):
        text = re.sub(r'\([^()]*\)', '', text)
    text = ' '.join(text.split())
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chosen = []
    for sentence in sentences[:2]:
        if len((' '.join(chosen + [sentence])).split()) > 24:
            break
        chosen.append(sentence)
    if chosen:
        return ' '.join(chosen)
    words = text.split()
    return ' '.join(words[:24]) + (' ...' if len(words) > 24 else '')


def clean_topic(text):
    text=re.sub(r'\bsilk printing\b','silk-screen printing',text,flags=re.I)
    aliases = {'byceclekick':'bicycle kick','bicyclekick':'bicycle kick',
               'bicylekick':'bicycle kick','fotbla':'football','footbal':'football',
               'futbal':'football','fotball':'football'}
    vocabulary = {'bicyclekick':'bicycle kick','football':'football',
                  'photosynthesis':'photosynthesis','gravity':'gravity',
                  'volcano':'volcano','electricity':'electricity','planet':'planet'}
    def fix(match):
        word = match.group(0).lower()
        if word in aliases:
            return aliases[word]
        if len(word) >= 6:
            close = get_close_matches(word,vocabulary,n=1,cutoff=0.82)
            if close:
                return vocabulary[close[0]]
        return match.group(0)
    return re.sub(r'[A-Za-z]+',fix,text).strip(' ?.!')


def search_topic(message):
    text = message.strip().rstrip('?.!')
    # Remove conversational wrapping rather than requiring a command or prefix.
    text = re.sub(r'\s*[,;]?\s*(?:can|could|would) you(?: please)? explain(?: it)?$','',text,flags=re.I)
    text = re.sub(r'^(?:hey[,!]?\s+)?(?:i (?:was |am )?(?:wondered|wondering|curious)(?: about)?|i(?:\'d| would) like to know|i (?:want|wanted) to know)\s+','',text,flags=re.I)
    explicit = re.match(r'^(?:search(?: online)?(?: for)?|look up|wiki|simple|britannica|check)\s+(.+)',text,re.I)
    if explicit:
        return clean_topic(explicit.group(1))
    embedded = re.search(r'\b(?:what (?:is|are|was|were)|who (?:is|was)|how|why|where|when|explain|tell me about)\b',text,re.I)
    if embedded:
        text=text[embedded.start():]
    how = re.match(r'^how\s+(?:(?:does|do)\s+)?(.+?)\s+works?$',text,re.I)
    if how:
        return clean_topic(how.group(1))
    question = re.match(r'^(?:what (?:is|are|was|were)|who (?:is|was)|explain|tell me about|can you explain)\s+(.+)',text,re.I)
    if question:
        topic = re.sub(r'\s+(?:simply|in simple words|please)$','',question.group(1),flags=re.I)
        return clean_topic(topic)
    if re.match(r'^(why|how|where|when|which)\b',text,re.I):
        return clean_topic(text)
    if re.match(r'^(?:i am curious|i was wondering|i wondered|i want to know)',message,re.I) and text:
        return clean_topic(text)
    return None


def lookup(topic, source='simple'):
    blocked = request_filter(topic)
    if blocked:
        return blocked
    topic = topic.strip()
    if not topic or len(topic) > 200:
        return 'Please give a short topic. Example: /search gravity'
    return _lookup(topic, source, int(time.time() // 600))


@lru_cache(maxsize=64)
def _lookup(topic, source, time_bucket):
    britannica = 'https://www.britannica.com/search?' + urlencode({'query': topic})
    if source == 'britannica':
        return ('Britannica blocks automated reading from this computer. '
                'I have not read its results. You can search it here:\n' + britannica
                + '\n\nFor a short source answer, use /search ' + topic)
    domains = ['ru.wikipedia.org'] if source == 'ru' else (['simple.wikipedia.org', 'en.wikipedia.org'] if source == 'simple' else ['en.wikipedia.org'])
    try:
        with httpx.Client(headers=HEADERS, timeout=12, follow_redirects=False) as client:
            for domain in domains:
                api = f'https://{domain}/w/api.php'
                response = client.get(api, params={
                    'action': 'query', 'format': 'json', 'list': 'search',
                    'srsearch': topic, 'srlimit': 1, 'srnamespace': 0,
                })
                response.raise_for_status()
                hits = response.json().get('query', {}).get('search', [])
                if not hits:
                    continue
                title = hits[0]['title']
                response = client.get(api, params={
                    'action': 'query', 'format': 'json', 'prop': 'extracts|pageprops',
                    'exintro': 1, 'explaintext': 1, 'redirects': 1, 'titles': title,
                })
                response.raise_for_status()
                pages = response.json().get('query', {}).get('pages', {})
                for page in pages.values():
                    if 'disambiguation' in page.get('pageprops', {}):
                        return f'{topic} has several meanings. Try a more specific topic.'
                    extract = page.get('extract', '')
                    if not extract:
                        continue
                    title = page['title']
                    url = f'https://{domain}/wiki/' + quote(title.replace(' ', '_'), safe='')
                    name = 'Simple English Wikipedia' if domain.startswith('simple.') else 'Wikipedia'
                    return (f'{title}\n\nShort source answer:\n{short_answer(extract)}'
                            f'\n\nSource: {name}\n{url}'
                            '\n\nThis is a shortened source excerpt, not a newly learned GPT answer.')
        return 'I could not find an encyclopedia entry. Try a shorter, more specific topic.'
    except (httpx.HTTPError, ValueError, KeyError):
        return ('I could not retrieve a source right now. Try again later. '
                'I will not guess an online answer.')
