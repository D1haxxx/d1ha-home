"""Small explicit tools: live date/time and limited arithmetic, never Python eval."""
import ast
import json
from pathlib import Path
from datetime import datetime
import math
import operator
from fractions import Fraction
import re
from zoneinfo import ZoneInfo

TIMEZONE = 'Asia/Nicosia'
SLANG = json.loads(Path(__file__).with_name('slang.json').read_text(encoding='utf-8'))['terms']
OPERATIONS = {ast.Add: operator.add, ast.Sub: operator.sub,
              ast.Mult: operator.mul, ast.Div: operator.truediv}


def calculate(expression):
    if len(expression) > 100:
        raise ValueError('Expression is too long')
    tree = ast.parse(expression, mode='eval')
    if sum(1 for _ in ast.walk(tree)) > 40:
        raise ValueError('Expression is too complex')

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = Fraction(str(node.value))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node,ast.BinOp) and isinstance(node.op,ast.Pow):
            base,exponent=visit(node.left),visit(node.right)
            if exponent.denominator!=1 or abs(exponent)>8:raise ValueError('Exponent too large')
            value=base**int(exponent)
        elif isinstance(node, ast.BinOp) and type(node.op) in OPERATIONS:
            value = OPERATIONS[type(node.op)](visit(node.left), visit(node.right))
        else:
            raise ValueError('Use numbers, parentheses, and + - * / only')
        if abs(value) > 1e12 or not math.isfinite(value):
            raise ValueError('Number is too large')
        return value
    return visit(tree.body)


def number_text(value):
    return str(value.numerator) if isinstance(value,Fraction) and value.denominator==1 else format(float(value),'.12g')


def arithmetic_reply(message):
    text=message.casefold().strip().replace('×','*').replace('÷','/').replace('−','-')
    text=text.replace("what's",'what is').replace('whats','what is')
    text=re.sub(r'^(?:please\s+)?(?:what is|how much is|what does|calculate|compute|solve|work out|посчитай|вычисли|сколько будет|чему равно)\s*','',text)
    text=re.sub(r'\s*(?:equal|equals|please|равно)\s*[?.!]*$','',text).rstrip('?.! =').strip()
    words={'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
    for word,number in words.items():text=re.sub(r'\b'+word+r'\b',str(number),text)
    for word,symbol in [('divided by','/'),('multiplied by','*'),('times','*'),('plus','+'),('minus','-'),('плюс','+'),('минус','-'),('умножить на','*'),('разделить на','/')]:
        text=re.sub(r'\b'+word+r'\b',symbol,text)
    text=re.sub(r'(?<=\d)\s*x\s*(?=\d)','*',text)
    text=text.replace('^','**').replace(',','.')
    percent=re.fullmatch(r'([0-9.]+)\s*(?:%|percent|процентов)\s*(?:of|от)\s*([0-9.]+)',text)
    if percent:text=f'({percent[1]}/100)*{percent[2]}'
    if not re.fullmatch(r'[0-9.\s()+*/-]+',text) or not any(c.isdigit() for c in text):return None
    try:return f'{text} = {number_text(calculate(text))} (calculator)'
    except ZeroDivisionError:return 'Division by zero is undefined. (calculator)'
    except (ValueError,SyntaxError,OverflowError,RecursionError):return 'Please use a short calculation with numbers, parentheses and + - * /; powers are limited to 8.'


def slang_reply(message):
    text = message.lower().strip().rstrip('?.!')
    if text in ('slang', 'slang list', 'what slang do you know'):
        return 'Slang glossary: ' + ', '.join(SLANG) + '. Ask: what does sus mean?'
    patterns = [r"what (?:does|do) (.+?) mean", r"(?:what is|define|explain|meaning of) (.+)",
                r"(?:use|give me an example of) (.+?)(?: in a sentence)?"]
    for pattern in patterns:
        match = re.fullmatch(pattern, text)
        if match:
            term = match.group(1).strip(' \"\'')
            if term in SLANG:
                entry = SLANG[term]
                if text.startswith(('use ', 'give me an example of ')):
                    return entry['example'] + ' (slang glossary)'
                return entry['meaning'] + ' (slang glossary; context matters)'
    return None


def tool_reply(message):
    arithmetic=arithmetic_reply(message)
    if arithmetic:return arithmetic
    slang = slang_reply(message)
    if slang:
        return slang
    russian = russian_tools(message)
    if russian:
        return russian
    text = message.strip().lower().replace("what's", 'what is').replace('whats', 'what is')
    text = text.rstrip('?.!').strip()
    if re.search(r'\b(date|day)\b', text) and (
        re.search(r'\b(today|current|now)\b', text) or text in ('what day is it', 'tell me the date')):
        now = datetime.now(ZoneInfo(TIMEZONE))
        return f'Today is {now.strftime("%A, %d %B %Y")}. (Live clock: {TIMEZONE})'
    if text in ('what time is it', 'what is the time', 'tell me the time', 'time now'):
        now = datetime.now(ZoneInfo(TIMEZONE))
        return f'It is {now:%H:%M:%S}. (Live clock: {TIMEZONE})'
    expression = re.sub(r'^(what is|calculate|compute|solve)\s+', '', text)
    expression = expression.replace('×', '*').replace('÷', '/')
    if re.fullmatch(r'[0-9.\s()+*/-]+', expression) and any(c.isdigit() for c in expression):
        try:
            value = calculate(expression)
            return f'{expression} = {value:g} (calculator)'
        except ZeroDivisionError:
            return 'Division by zero is undefined. (calculator)'
        except (ValueError, SyntaxError, OverflowError, RecursionError):
            return 'Try a short calculation using numbers, parentheses, and + - * /. (calculator)'
    return None


def russian_tools(message):
    text=message.lower().strip().rstrip('?.!')
    if text in ('какая сегодня дата','какое сегодня число','какой сегодня день','сегодняшняя дата','дата'):
        now=datetime.now(ZoneInfo(TIMEZONE))
        return f'Сегодня {now:%d.%m.%Y}. Часовой пояс: {TIMEZONE}.'
    if text in ('который час','сколько сейчас времени','какое сейчас время','время'):
        now=datetime.now(ZoneInfo(TIMEZONE))
        return f'Сейчас {now:%H:%M:%S}. Часовой пояс: {TIMEZONE}.'
    query=re.match(r'^(?:что значит|что означает|объясни сленг)\s+["\']?([a-z]+)["\']?$',text)
    if query:
        meanings={'bet':'Неформальное согласие: «договорились».','bruh':'Неформальное обращение или реакция удивления.',
                  'sus':'Подозрительный.','lit':'Классный или захватывающий.','rizz':'Обаяние, особенно при флирте.',
                  'ngl':'Сокращение not gonna lie: «честно говоря».'}
        if query.group(1) in meanings:return meanings[query.group(1)]+' (Словарь сленга.)'
    expression=re.sub(r'^(?:посчитай|вычисли|сколько будет|чему равно)\s+','',text)
    expression=expression.replace('×','*').replace('÷','/').replace(',','.')
    if expression!=text and re.fullmatch(r'[0-9.\s()+*/-]+',expression):
        try:return f'{expression} = {calculate(expression):g} (калькулятор)'
        except ZeroDivisionError:return 'Делить на ноль нельзя. (Калькулятор.)'
        except (ValueError,SyntaxError,OverflowError,RecursionError):return 'Напиши короткий пример с числами и знаками + - * /.'
    return None
