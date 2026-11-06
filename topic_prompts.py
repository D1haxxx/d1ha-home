"""Explicit topic matching for a small trained expert, not general understanding."""
from functools import lru_cache
from pathlib import Path
import json,re

@lru_cache(maxsize=1)
def lessons():
    rows=json.loads((Path(__file__).parent/'training_1_5/upgrade_1_5.json').read_text(encoding='utf-8'))
    result=[]
    for row in rows:
        question=row['question']
        if question.startswith('what is '):
            topic=re.sub(r'^(?:a|an) ','',question[8:].rstrip('?'))
        elif question.startswith('что такое '):topic=question[10:]
        else:continue
        result.append((topic,question,row['answer']))
    return sorted(result,key=lambda item:len(item[0]),reverse=True)


def topic_prompt(message):
    text=' '.join(message.casefold().split()).replace('silk printing','screen printing').replace('silk-screen printing','screen printing')
    if len(text.split())>20 or re.search(r'\b(?:not|versus|difference|compare|wrong)\b|не является|сравни|отлич',text):return None
    if not re.match(r'^(?:what|how|explain|describe|tell|can|could|please|что|как|объясни|расскажи|помоги|зачем|можешь)',text):return None
    matches=[row for row in lessons() if re.search(r'(?<!\w)'+re.escape(row[0])+r'(?!\w)',text)]
    if len(matches)!=1:return None
    return matches[0]
