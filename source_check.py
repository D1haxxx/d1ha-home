"""Compare short excerpts from Wikipedia and independently published references.
Shared words are a relevance signal, never proof that a claim is true.
"""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin, quote
import re
import os
import json
import socket
import ipaddress
import time
import xml.etree.ElementTree as ET
import httpx
from online_lookup import HEADERS, short_answer
from safety import request_filter, safe_source_text

PUBLISHERS = {
    'nasa.gov': 'NASA', 'noaa.gov': 'NOAA', 'britannica.com': 'Britannica',
    'cern.ch': 'CERN', 'home.cern': 'CERN', 'metoffice.gov.uk': 'Met Office',
    'docs.python.org': 'Python documentation', 'ligo.caltech.edu': 'LIGO',
    'nist.gov': 'NIST', 'energy.gov': 'US Department of Energy',
    'usgs.gov': 'US Geological Survey', 'si.edu': 'Smithsonian',
    'nih.gov': 'NIH', 'cdc.gov': 'CDC', 'who.int': 'WHO',
    'esa.int': 'European Space Agency', 'royalsociety.org': 'Royal Society',
    'python.org': 'Python documentation',
    'nationalgalleries.org': 'National Galleries of Scotland',
    'npg.org.uk': 'National Portrait Gallery', 'vam.ac.uk': 'Victoria and Albert Museum',
    'speedballart.com': 'Speedball Art',
    'fifa.com': 'FIFA', 'uefa.com': 'UEFA', 'theifab.com': 'IFAB',
    'olympics.com': 'Olympics', 'developer.mozilla.org': 'MDN',
    'nhs.uk': 'NHS', 'medlineplus.gov': 'MedlinePlus',
    'unicef.org': 'UNICEF', 'un.org': 'United Nations',
    'ushmm.org': 'United States Holocaust Memorial Museum',
    'history.state.gov': 'US Office of the Historian',
}
STOP = set('a an the is are was were of to in on for and or by with what why how who does do explain me tell about please today'.split())


def publisher(url):
    try:
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
            return None
        host = parsed.hostname or ''
    except ValueError:
        return None
    return next((name for domain, name in PUBLISHERS.items()
                 if host == domain or host.endswith('.' + domain)), None)


def terms(text):
    text=re.sub(r'\bscreenprinting\b','screen printing',text,flags=re.I)
    return set(re.findall(r'[^\W\d_]{3,}', text.lower())) - STOP


class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.active = False
        self.parts = []
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'footer', 'header'):
            self.skip += 1
        if tag == 'p' and not self.skip:
            self.active = True
            self.parts = []

    def handle_endtag(self, tag):
        if tag == 'p' and self.active:
            text = ' '.join(' '.join(self.parts).split())
            if len(text.split()) >= 8:
                self.paragraphs.append(text)
            self.active = False
        if tag in ('script', 'style', 'nav', 'footer', 'header'):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if self.active and not self.skip:
            self.parts.append(data)


def external_excerpt(url, topic, discovered=False):
    try:
        with httpx.Client(headers=HEADERS, timeout=6, follow_redirects=False, trust_env=False) as client:
            for _ in range(4):
                name = publisher(url)
                request_url=url
                options={}
                if discovered:
                    request_url,host=public_target(url)
                    name=name or host
                    options={'headers':{'Host':host},'extensions':{'sni_hostname':host}}
                if not name:
                    return None
                # Validate every redirect and cap bytes read from source pages.
                with client.stream('GET', request_url, **options) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get('location', ''))
                        continue
                    response.raise_for_status()
                    if 'text/html' not in response.headers.get('content-type', ''):
                        return None
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) >= 500_000:
                            break
                parser = Paragraphs()
                parser.feed(bytes(data).decode('utf-8', errors='replace'))
                candidates = [p for p in parser.paragraphs if terms(p) & terms(topic) and safe_source_text(p)]
                if not candidates:
                    return None
                best = max(candidates, key=lambda p: (len(terms(p) & terms(topic)),
                           len(terms(p[:80]) & terms(topic))))
                return {'publisher': name, 'url': url, 'text': best}
    except (httpx.HTTPError, ValueError, OSError):
        return None
    return None


def wiki_evidence(topic, language='en'):
    with httpx.Client(headers=HEADERS, timeout=8) as client:
        api = 'https://ru.wikipedia.org/w/api.php' if language=='ru' else 'https://en.wikipedia.org/w/api.php'
        r = client.get(api, params={'action':'query','format':'json','list':'search',
                                   'srsearch':topic,'srlimit':1})
        r.raise_for_status()
        hits = r.json().get('query', {}).get('search', [])
        if not hits:
            return None, []
        title = hits[0]['title']
        r = client.get(api, params={'action':'query','format':'json',
             'prop':'extracts|extlinks|pageprops|langlinks','lllang':'en','exintro':1,'explaintext':1,
             'titles':title,'redirects':1,'ellimit':100})
        r.raise_for_status()
        page = next(iter(r.json().get('query', {}).get('pages', {}).values()), {})
        if not page.get('extract') or not safe_source_text(page.get('extract', '')[:1000]) or 'disambiguation' in page.get('pageprops', {}):
            return None, []
        title = page['title']
        source = {'publisher':'Wikipedia','url':('https://ru.wikipedia.org/wiki/' if language=='ru' else 'https://en.wikipedia.org/wiki/')+quote(title.replace(' ','_'),safe=''),
                  'text':page['extract'], 'title':title}
        english_title=next((entry.get('*') for entry in page.get('langlinks',[]) if entry.get('lang')=='en'),title)
        source['search_topic']=english_title
        links=[]
        for entry in page.get('extlinks', []):
            url=entry.get('*','')
            if url.startswith('http://'):
                url='https://'+url[len('http://'):]
            if publisher(url):
                links.append(url)
        # Prefer explanatory NASA pages over images and technical news.
        if re.search(r'\bgravity\b',english_title,re.I):
            links.insert(0,'https://spaceplace.nasa.gov/what-is-gravity/en/')
        # Use the easier edition for the main excerpt when available. It is
        # still the same publisher; never count it as independent confirmation.
        try:
            if language=='ru':return source,links
            simple = client.get('https://simple.wikipedia.org/w/api.php', params={
                'action':'query','format':'json','prop':'extracts','exintro':1,
                'explaintext':1,'redirects':1,'titles':title})
            simple.raise_for_status()
            easier = next(iter(simple.json().get('query', {}).get('pages', {}).values()), {})
            if easier.get('extract') and 'missing' not in easier and safe_source_text(easier['extract'][:1000]):
                source['text'] = easier['extract']
                source['url'] = 'https://simple.wikipedia.org/wiki/' + quote(easier['title'].replace(' ','_'),safe='')
        except (httpx.HTTPError,ValueError):
            pass
        return source, links


def nasa_search(topic):
    links = []
    try:
        with httpx.Client(headers=HEADERS, timeout=6) as client:
            for domain in ('www.nasa.gov', 'science.nasa.gov'):
                response = client.get(f'https://{domain}/wp-json/wp/v2/search',
                                      params={'search': topic, 'per_page': 4})
                response.raise_for_status()
                hits = response.json()
                if not isinstance(hits, list):
                    continue
                for hit in hits:
                    if not isinstance(hit, dict):
                        continue
                    url = hit.get('url', '')
                    if publisher(url) and '/image-article/' not in url and terms(hit.get('title', '')) & terms(topic):
                        links.append(url)
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return links


def medical_search(topic):
    """Use the National Library of Medicine's own search index."""
    try:
        with httpx.Client(headers=HEADERS, timeout=8) as client:
            response = client.get('https://wsearch.nlm.nih.gov/ws/query', params={
                'db': 'healthTopics', 'term': topic, 'retmax': 3})
            response.raise_for_status()
            if len(response.content)>500_000:
                return []
            root = ET.fromstring(response.content)
            links=[]
            for doc in root.findall('.//document'):
                titles=' '.join(c.text or '' for c in doc.findall('content')
                                if c.get('name') in ('title', 'altTitle'))
                url=doc.get('url','')
                if publisher(url) and terms(titles) & terms(topic):
                    links.append(url)
            return links
    except (httpx.HTTPError, ET.ParseError, ValueError):
        return []


# Topic routing is explicit and inspectable; it is not a trained classifier.
TOPIC_SOURCES = {
    'health': ('medlineplus.gov', 'nhs.uk', 'who.int', 'nih.gov'),
    'space': ('nasa.gov', 'esa.int'),
    'programming': ('docs.python.org', 'developer.mozilla.org'),
    'football': ('fifa.com', 'uefa.com', 'theifab.com'),
    'sport': ('olympics.com',),
    'earth': ('noaa.gov', 'usgs.gov', 'metoffice.gov.uk'),
    'history': ('si.edu', 'history.state.gov', 'ushmm.org'),
    'science': ('cern.ch', 'nist.gov', 'royalsociety.org', 'energy.gov'),
    'art': ('nationalgalleries.org', 'npg.org.uk', 'vam.ac.uk', 'speedballart.com'),
    'general': ('britannica.com', 'si.edu', 'un.org'),
}
TOPIC_PATTERNS = {
    'art': r'screen.?print|silk.?screen|silk printing|printmaking|lithograph|painting|sculpture|трафарет|шелкограф|шёлкограф',
    'programming': r'python|javascript|html|css|programming|coding|\bcode\b|algorithm|программ|питон|код',
    'football': r'football|soccer|bicycle kick|offside|футбол|офсайд',
    'sport': r'basketball|tennis|swimming|olympic|sport|баскетбол|теннис|спорт',
    'health': r'health|depress|anxiety|puberty|consent|disease|symptom|medicine|sexual|pregnan|mental|cancer|diabet|здоров|депресс|тревог|болезн|полов|берем',
    'space': r'gravity|planet|space|astronom|galaxy|black hole|moon|solar|звезд|звёзд|космос|планет|гравитац|лун',
    'earth': r'climate|weather|earthquake|volcano|ocean|hurricane|климат|погод|землетряс|вулкан|океан',
    'history': r'history|historical|holocaust|world war|ancient|истори|войн|древн|холокост',
    'science': r'physics|chemistry|atom|particle|electric|energy|физик|хими|атом|энерги',
}


def topic_category(topic):
    return next((category for category, pattern in TOPIC_PATTERNS.items()
                 if re.search(pattern, topic, re.I)), 'general')


def relevant_url(url, category):
    host=urlparse(url).hostname or ''
    return any(host==domain or host.endswith('.'+domain)
               for domain in TOPIC_SOURCES[category])


def topic_search(topic):
    category=topic_category(topic)
    links=trusted_search(topic)
    if category=='art' and re.search(r'screen.?print|silk.?screen|silk printing|шелкограф|шёлкограф',topic,re.I):
        links=[
            'https://www.nationalgalleries.org/art-and-artists/glossary-terms/screenprinting',
            'https://www.npg.org.uk/collections/explore/glossary-of-art-terms/silk-screen-printing',
            'https://www.vam.ac.uk/articles/what-is-print',
        ]+links
    elif category=='health':
        links=medical_search(topic)+links
    elif category=='space':
        links=nasa_search(topic)+links
    elif category=='programming':
        if re.search(r'python|питон',topic,re.I):
            if re.search(r'list|спис',topic,re.I):
                links.insert(0,'https://docs.python.org/3/tutorial/datastructures.html')
            elif re.search(r'loop|цикл|function|функц',topic,re.I):
                links.insert(0,'https://docs.python.org/3/tutorial/controlflow.html')
    return [url for url in links if relevant_url(url,category)]


def trusted_search(topic):
    """Discover pages independently of Wikipedia; read only approved publishers."""
    try:
        with httpx.Client(headers=HEADERS, timeout=8, follow_redirects=False) as client:
            response = client.get('https://www.bing.com/search', params={
                'q': topic+' ('+' OR '.join('site:'+domain for domain in TOPIC_SOURCES[topic_category(topic)])+')', 'format': 'rss'})
            response.raise_for_status()
            if len(response.content) > 500_000:
                return []
            root = ET.fromstring(response.content)
            return [url for item in root.findall('.//item')
                    if publisher(url := item.findtext('link', ''))
                    and relevant_url(url,topic_category(topic))
                    and terms(item.findtext('title','')) & terms(topic)][:8]
    except (httpx.HTTPError, ET.ParseError, ValueError):
        return []


def cross_check(topic, language='en', max_sources=3):
    blocked = request_filter(topic)
    if blocked:
        return blocked
    if not topic.strip() or len(topic) > 200:
        return 'Please give a topic under 200 characters. Example: /check gravity'
    return search_overview(topic.strip(), int(time.time() // 600), language)


@lru_cache(maxsize=64)
def _cross_check(topic, time_bucket, language='en', max_sources=3):
    # Independent discovery is attempted even if Wikipedia is unavailable.
    with ThreadPoolExecutor(max_workers=2) as pool:
        wiki_job = pool.submit(wiki_evidence, topic, language)
        topic_job = pool.submit(topic_search, topic)
        try:
            wiki, links = wiki_job.result()
        except (httpx.HTTPError, ValueError, KeyError):
            wiki, links = None, []
        direct_links = topic_job.result()
    if language=='ru' and wiki and wiki.get('search_topic')!=wiki.get('title'):
        direct_links+=topic_search(wiki['search_topic'])
    category=topic_category(wiki.get('search_topic',topic) if wiki else topic)
    links=[url for url in links if relevant_url(url,category)]
    preferred=[url for url in links if 'spaceplace.nasa.gov/what-is-gravity/' in url]
    links = list(dict.fromkeys(preferred + direct_links + links))
    # Wikipedia editions share a publisher and count as one source, not two.
    candidates=[]
    counts={}
    for url in links:
        name=publisher(url)
        if counts.get(name,0)<2:
            candidates.append(url);counts[name]=counts.get(name,0)+1
        if len(candidates)>=6:
            break
    with ThreadPoolExecutor(max_workers=6) as pool:
        found=list(pool.map(lambda url: external_excerpt(url, wiki.get('search_topic',wiki['title']) if wiki else topic), candidates))
    sources=[]
    seen=set()
    for source in found:
        if source and source['publisher'] not in seen:
            sources.append(source);seen.add(source['publisher'])
        if len(sources)>=max_sources:
            break
    if wiki and len(sources)<max_sources:
        sources.append(wiki)
    if not sources:
        return 'No suitable readable source was found. Try a more specific topic; I will not guess.'
    title = wiki.get('search_topic',wiki['title']) if wiki else topic
    result=[f"Topic found: {title}"]
    for index, source in enumerate(sources,1):
        result.append(f"{index}. {source['publisher']}\n{short_answer(source['text'])}\n{source['url']}")
    if len(sources)==1 and max_sources>1:
        result.append('Cross-check incomplete: only one publisher could be read. This answer is not independently verified.')
    elif len(sources)>1:
        overlap=set.intersection(*(terms(s['text']) for s in sources))
        shared=sorted(overlap & terms(title))
        if shared:
            result.append('Topic overlap: '+', '.join(shared[:5])+'.')
        result.append(f'Compared {len(sources)} publishers. These are short source excerpts; shared words do not prove factual agreement. Verification remains incomplete.')
    return '\n\n'.join(result)


def public_target(url):
    """Pin HTTPS to a checked public IP, preserving TLS hostname verification."""
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or not parsed.hostname:
        raise ValueError('Public HTTPS sources only')
    host=parsed.hostname.encode('idna').decode('ascii')
    addresses=list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError('Private network sources are blocked')
    address=addresses[0]
    authority='['+address+']' if ':' in address else address
    return 'https://'+authority+(parsed.path or '/')+('?' + parsed.query if parsed.query else ''),host


def configured_search_key():
    key=os.environ.get('BRAVE_SEARCH_API_KEY','').strip()
    path=__import__('pathlib').Path(__file__).with_name('search_config.json')
    if not key and path.exists():
        try:key=json.loads(path.read_text(encoding='utf-8')).get('brave_api_key','').strip()
        except (ValueError,AttributeError,OSError):return ''
    return key


def ranked_search(topic):
    key=configured_search_key()
    if key:
        try:
            with httpx.Client(timeout=8,trust_env=False) as client:
                response=client.get('https://api.search.brave.com/res/v1/web/search',params={'q':topic,'count':10,'safesearch':'strict'},headers={'X-Subscription-Token':key,'Accept':'application/json'})
                response.raise_for_status()
                return [(hit.get('title',''),hit.get('url','')) for hit in response.json().get('web',{}).get('results',[])[:10]]
        except (httpx.HTTPError,ValueError,TypeError):pass
    """The search provider's first ten results, not a claim of the ten best sites."""
    try:
        with httpx.Client(headers=HEADERS,timeout=8,trust_env=False) as client:
            response=client.get('https://www.bing.com/search',params={'q':topic,'format':'rss'})
            response.raise_for_status()
            if len(response.content)>500_000:return []
            root=ET.fromstring(response.content)
            return [(item.findtext('title',''),item.findtext('link',''))
                    for item in root.findall('.//item')[:10]]
    except (httpx.HTTPError,ET.ParseError,ValueError):
        return []


@lru_cache(maxsize=64)
def search_overview(topic,time_bucket,language='en'):
    results=ranked_search(topic)
    candidates=[];hosts=set()
    for title,url in results:
        host=urlparse(url).hostname
        if host and host not in hosts and len(terms(title)&terms(topic))>=min(2,len(terms(topic))):
            hosts.add(host);candidates.append(url)
    fallback=False
    if not candidates:
        fallback=True
        candidates=topic_search(topic)[:10]
    with ThreadPoolExecutor(max_workers=3) as pool:
        found=list(pool.map(lambda url:external_excerpt(url,topic,discovered=True),candidates))
    sources=[source for source in found if source]
    if not sources and not fallback:
        fallback=True
        with ThreadPoolExecutor(max_workers=3) as pool:
            found=list(pool.map(lambda url:external_excerpt(url,topic,discovered=True),topic_search(topic)[:10]))
        sources=[source for source in found if source]
    if not sources:
        try:wiki,_=wiki_evidence(topic,language)
        except (httpx.HTTPError,ValueError,KeyError):wiki=None
        if wiki:sources=[wiki]
    if not sources:
        return 'I could not read relevant sources for this search. Try a more specific question.'
    # Extractive overview: select concise source sentences. Never call word
    # overlap factual agreement; the tiny chat model cannot verify contradictions.
    overview=[];used=set()
    for source in sources:
        excerpt=short_answer(source['text'])
        words=terms(excerpt)
        if not excerpt or (used and len(words-used)<3):continue
        overview.append(excerpt);used.update(words)
        if len(overview)==3:break
    lines=[topic,'Short source-based overview:',' '.join(overview),'Sources:']
    lines += [f"{index}. {source['publisher']}: {source['url']}" for index,source in enumerate(sources,1)]
    lines.append(f'Read {len(sources)} pages. Inspected {len(results)} search results; blocked, duplicate or unrelated pages were omitted.')
    if fallback:lines.append('The search results were unavailable or unrelated, so topic-specific sources were used as a fallback.')
    lines.append('This overview combines short excerpts. Agreement between sources has not been verified.')
    return '\n\n'.join(lines)
