"""Russian-language routing and interface text; not a general translator."""
import re


def is_russian(text):
    return bool(re.search('[А-Яа-яЁё]',text))


def russian_topic(message):
    text=message.strip().rstrip('?.!')
    text=re.sub(r'^(?:мне интересно|я (?:хотел|хотела|хочу)(?: бы)? узнать)\s*[, :]?\s*','',text,flags=re.I)
    text=re.sub(r'[, ]+(?:можешь|можете) объяснить$','',text,flags=re.I)
    conversational=re.match(r'^(?:ты )?(?:можешь|можете)(?: пожалуйста)? (?:объяснить|рассказать)(?: мне)?(?: про| о| об)?[, ]+(.+)',text,re.I)
    if conversational:
        text=conversational.group(1).strip()
        inner=russian_topic(text)
        return inner or text
    tail=re.match(r'^как\s+(.+?)\s+работает$',text,re.I)
    if tail:return tail.group(1)
    prefix=r'^(?:что такое|что значит|кто такой|кто такая|расскажи(?: мне)? (?:о|об|про)|объясни(?: мне)?|как (?:работает|работают|устроен|устроена)|найди(?: в интернете)?|поиск)\s+(.+)'
    match=re.match(prefix,text,re.I)
    if match:return match.group(1).strip()
    if re.match(r'^(?:почему|как|где|когда|зачем|кто|что|какой|какая|сколько)\b',text,re.I):return text
    return None


def localize_search(text):
    replacements={
        'Source: Simple English Wikipedia':'Источник: Simple English Wikipedia',
        'Source: Wikipedia':'Источник: Википедия',
        'Only one source was readable; I could not independently confirm it.':'Удалось прочитать только один источник. Независимое подтверждение не получено.',
        'Multiple publishers were consulted; full agreement is not automatically verified.':'Проверены разные издатели, но полное совпадение фактов автоматически не доказано.',
        'No suitable readable source was found. Try a more specific topic; I will not guess.':'Не удалось прочитать подходящий источник. Уточни тему — я не буду угадывать.',
        'Online lookup failed. I could not check sources, so I will not guess an answer.':'Не удалось проверить источники онлайн. Попробуй позже — я не буду угадывать.',
        'I could not find an encyclopedia entry. Try a shorter, more specific topic.':'Статья не найдена. Попробуй более короткий и точный запрос.',
        'I could not retrieve a source right now. Try again later. I will not guess an online answer.':'Сейчас не удалось получить источник. Попробуй позже.',
        'I could not identify a clear article. Please give a more specific topic.':'Не удалось выбрать подходящую статью. Уточни тему.',
    }
    for source,target in replacements.items():text=text.replace(source,target)
    return text


def russian_intent(text):
    """Map a narrow set of Russian phrasings to practiced prompts, not answers."""
    if re.search(r'\bкак\b.{0,35}(?:дела|поживаешь|чувствуешь)',text):return 'как дела'
    if re.search(r'^(?:привет|здравствуй|здравствуйте|добрый день)\b',text):return 'привет'
    if re.search(r'спасибо|благодарю',text):return 'спасибо'
    if re.search(r'(?:код|программ).*(?:ошиб|не работ)|(?:ошиб).*(?:код|программ)',text):return 'как найти ошибку'
    if re.search(r'(?:ты|тво).*(?:ошиб|невер|неправ|неточ)',text):return 'ты можешь ошибаться'
    if re.fullmatch(r'(?:что ты (?:умеешь|можешь)(?: делать)?|чем ты можешь помочь|какие у тебя возможности|твои возможности)',text):return 'что ты умеешь'
    definitions={'переменн':'что такое переменная','цикл':'что такое цикл','спис':'что такое список',
                 'строк':'что такое строка','функци':'что такое функция','нейросет':'что такое нейросеть',
                 'токен':'что такое токен'}
    if re.search(r'что|объясни|расскажи|для чего|зачем|почему',text):
        for root,prompt in definitions.items():
            if root in text and not re.search(r'менстру|стих|песн|поэм',text):return prompt
    return None


def english_intent(text):
    match=re.fullmatch(r'(?:explain|define|describe|what (?:is|are)|tell me about) (?:a |an |the )?(?:python )?(loops?|variables?|lists?|strings?|functions?)(?: in python)?',text)
    if not match:
        match=re.fullmatch(r'what (?:does|do) (?:a |the )?(?:python )?(loops?|variables?|lists?|strings?|functions?) do',text)
    if match:
        noun=match.group(1).rstrip('s')
        return f'what is a {noun}?'
    return None
