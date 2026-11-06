"""Shared model loading for terminal and Telegram clients."""
import json
import re
from difflib import get_close_matches
from pathlib import Path
import torch
from model import MicroGPT
from cool_mode import configure_cpu
from topic_prompts import topic_prompt
from tools import tool_reply, arithmetic_reply
from online_lookup import lookup, search_topic
from source_check import cross_check
from safety import request_filter
from bilingual import is_russian, russian_topic, localize_search, russian_intent, english_intent


class D1haChat:
    def __init__(self):
        configure_cpu()
        folder = Path(__file__).parent
        release_path = folder / 'release.json'
        release = json.loads(release_path.read_text()) if release_path.exists() else {}
        model_name = release.get('checkpoint', 'd1ha_model.pt')
        if Path(model_name).name != model_name:
            raise ValueError('Checkpoint must be a filename beside runtime.py')
        path = folder / model_name
        if not path.exists():
            raise FileNotFoundError(f'Model missing: {model_name}. Run its training script first.')
        saved = torch.load(path, map_location='cpu', weights_only=True)
        self.version = release.get('version', saved.get('version', '1.0'))
        self.checkpoint_name = model_name
        self.folder = folder
        self.chars = saved['chars']
        self.model = MicroGPT(len(self.chars) + 1, **saved['settings'])
        self.model.load_state_dict(saved['model_state'])
        self.model.eval()
        self.models = {'d1ha': (self.model, self.chars)}
        # A wording check, not a calibrated measure of the model's confidence.
        self.known_questions = set()
        lessons = [folder/'conversations_focused.txt',folder/'training_files'/'russian_conversations.txt']
        for lesson in lessons:
            if lesson.exists():
                for line in lesson.read_text(encoding='utf-8').splitlines():
                    if line.startswith('User: '):
                        self.known_questions.add(self.normalise(line[6:]))

    @staticmethod
    def normalise(message):
        return ' '.join(message.lower().strip().rstrip('?!.').split())

    MODEL_NAMES = {'d1ha': 'D1ha 1.6', 'd1ha-1-5': 'D1ha 1.5', 'd1ha-1-4': 'D1ha 1.4', 'd1ha-1-3': 'D1ha 1.3', 'd1ha-1': 'D1ha 1', 'd1ha-1-1': 'D1ha 1.1', 'd1ha-1-2': 'D1ha 1.2', 'classic': 'Classic (small)'}
    MODEL_FILES = {'d1ha-1-5':'d1ha_1_5.pt', 'd1ha-1-4':'d1ha_1_4.pt', 'd1ha-1-3': 'd1ha_1_2_chat.pt', 'd1ha-1': 'd1ha_model.pt', 'd1ha-1-1': 'd1ha_1_1.pt', 'd1ha-1-2': 'd1ha_1_2_chat.pt', 'classic': 'd1ha_first_five.pt'}

    def selected_model(self, model_id):
        # Keep older lessons on their proven checkpoint; the new expert handles
        # the focused topics below. This is an explicit hybrid, not one giant LLM.
        if model_id=='d1ha' and self.version in ('1.5','1.6'):model_id='d1ha-1-4'
        if model_id not in self.MODEL_NAMES:
            model_id = 'd1ha'
        if model_id not in self.models:
            saved = torch.load(self.folder / self.MODEL_FILES[model_id], map_location='cpu', weights_only=True)
            model = MicroGPT(len(saved['chars']) + 1, **saved['settings'])
            model.load_state_dict(saved['model_state'])
            model.eval()
            self.models[model_id] = (model, saved['chars'])
        return self.models[model_id]

    def reply(self, message, memory=None):
        memory = {} if memory is None else memory
        if is_russian(message):memory['language']='ru'
        elif re.search('[A-Za-z]',message):memory['language']='en'
        memory['_neural_usage'] = {}
        result = self._reply(message, memory)
        counts = memory.pop('_neural_usage', {})
        memory['usage'] = {
            'input_characters': len(message), 'reply_characters': len(result),
            'prompt_tokens': counts.get('prompt_tokens', 0),
            'generated_tokens': counts.get('generated_tokens', 0),
            'model': memory.get('model', 'd1ha'), 'mode': memory.get('mode', 'deep'),
        }
        return result

    def _reply(self, message, memory):
        blocked = request_filter(message)
        if blocked:
            return blocked
        arithmetic=arithmetic_reply(message)
        if arithmetic:return arithmetic
        if self.version in ('1.5','1.6') and memory.get('model','d1ha') in ('d1ha','d1ha-1-5'):
            practiced=topic_prompt(message)
            if practiced:
                topic,prompt,expected=practiced
                memory['last_topic']=topic
                expert,chars=(self.model,self.chars) if memory.get('model','d1ha')=='d1ha' else self.selected_model('d1ha-1-5')
                answer=expert.reply(prompt,chars,temperature=0,max_new=180,usage=memory['_neural_usage'])
                # A narrow expert should abstain when generation drifts from
                # its practiced answer; do not present garbled text as knowledge.
                if answer==expected:return answer
                return self.search(topic,memory)
        if is_russian(message):
            return self.reply_russian(message,memory)
        identity = self.normalise(message)
        if identity in ('what is your name', 'whats your name', 'who are you', 'what version are you'):
            return f"I'm {self.MODEL_NAMES.get(memory.get('model', 'd1ha'), 'D1ha ' + self.version)}."
        local = tool_reply(message)
        if local:
            return local
        normal = self.normalise(message)
        greetings = {'hi', 'hello', 'hey', 'hello there', 'hi there', 'hello friend', 'yo', 'sup'}
        wellbeing = {'how are you', 'how are you doing', 'how is it going', 'how r u'}
        if memory.get('model', 'd1ha') in ('d1ha', 'd1ha-1-2') and normal in greetings | wellbeing:
            canonical = 'hi' if normal in greetings else 'how are you'
            model, chars = self.selected_model(memory.get('model','d1ha'))
            totals = {'prompt_tokens': 0, 'generated_tokens': 0}
            for _ in range(4):
                usage = {}
                candidate = model.reply(canonical, chars, temperature=0.35, top_k=2, usage=usage)
                for key in totals:
                    totals[key] += usage.get(key, 0)
                if candidate != memory.get('last_smalltalk'):
                    break
            memory['_neural_usage'] = totals
            memory['last_smalltalk'] = candidate
            return candidate
        followup = normal in ('tell me more', 'more please', 'give me an example', 'explain more', 'go on', 'why',
                              'how does it work', 'how does that work', 'why is that')
        if followup or re.search(r'\b(?:it|that|they|them)\b',normal):
            previous = memory.get('last_topic')
            if previous and (followup or re.match(r'^(how|why|what|does|can)\b',normal)):
                expanded = previous if followup else re.sub(r'\b(?:it|that|they|them)\b',previous,message,flags=re.I)
                return self.search(expanded, memory)
            if followup:
                return 'Which topic do you mean? For example: how gravity works.'
        canonical=english_intent(normal)
        familiar = bool(canonical) or normal in self.known_questions or bool(
            get_close_matches(normal, self.known_questions, n=1, cutoff=0.92))
        if familiar:
            prompt=canonical or message
            topic = search_topic(prompt)
            if topic:
                memory['last_topic'] = topic
            model, chars = self.selected_model(memory.get('model', 'd1ha'))
            return model.reply(prompt, chars, temperature=0, usage=memory['_neural_usage'])
        topic = search_topic(message)
        if topic:
            if normal.startswith('britannica '):
                return lookup(topic, 'britannica')
            return self.search(topic, memory)
        if message.rstrip().endswith('?') or re.match(r'^(can|could|is|are|does|do)\b',normal):
            return self.search(message, memory)
        return ('Could you tell me a little more about what you mean? '
                'You can phrase your question normally, and I can look it up.')

    def reply_russian(self,message,memory):
        normal=self.normalise(message)
        name=self.MODEL_NAMES.get(memory.get('model','d1ha'),'D1ha '+self.version)
        if normal in ('как тебя зовут','кто ты','какая у тебя версия','какое у тебя имя','представься'):
            return f'Я {name}.'
        local=tool_reply(message)
        if local:return local
        followups={'расскажи подробнее','подробнее','продолжай','как это работает','почему так','а как это работает','можешь объяснить подробнее'}
        if normal in followups:
            if memory.get('last_topic'):return self.search(memory['last_topic'],memory)
            return 'О какой теме рассказать? Например: как работает гравитация.'
        normal={'превет':'привет','прив':'привет','как дила':'как дела'}.get(normal,normal)
        intent=russian_intent(normal)
        closest=get_close_matches(normal,self.known_questions,n=1,cutoff=0.92)
        canonical=intent or (normal if normal in self.known_questions else (closest[0] if closest else None))
        if canonical:
            model,chars=self.selected_model(memory.get('model','d1ha'))
            if not set('привет').issubset(chars):return 'Для русских ответов модели выбери D1ha 1.4. Более ранние модели обучались на английском.'
            prompt=''.join(c for c in canonical if c in chars)
            topic=russian_topic(prompt)
            if topic:memory['last_topic']=topic
            return model.reply(prompt,chars,temperature=0,usage=memory['_neural_usage'])
        topic=russian_topic(message)
        if topic:return self.search(topic,memory)
        if len(normal.split())<=5 or message.strip().endswith('?'):
            return self.search(normal,memory)
        return 'Расскажи немного подробнее, что ты имеешь в виду. Можно задать вопрос своими словами.'

    @staticmethod
    def search(topic, memory):
        language='ru' if is_russian(topic) or memory.get('language')=='ru' else 'en'
        if memory.get('mode', 'deep') == 'light':
            answer=cross_check(topic,language=language,max_sources=1)
        else:
            answer=cross_check(topic,language=language)
        match = re.match(r'Topic found: ([^\n]+)',answer)
        if not match and '\n\nShort source answer:' in answer:
            memory['last_topic'] = answer.split('\n', 1)[0]
        if match:
            memory['last_topic'] = match.group(1)
        result=readable_answer(answer)
        return localize_search(result) if language=='ru' else result


def readable_answer(answer):
    """Keep the answer and sources, without exposing the routing machinery."""
    if '\n\nShort source answer:' in answer:
        parts=answer.split('\n\n')
        title=parts[0]
        excerpt=next((p.removeprefix('Short source answer:\n') for p in parts if p.startswith('Short source answer:')), '')
        source=next((p for p in parts if p.startswith('Source:')), '')
        return f'{title}\n\n{excerpt}\n\n{source}'.strip()
    if not answer.startswith('Topic found:'):
        return answer
    parts=answer.split('\n\n')
    title=parts[0].removeprefix('Topic found: ')
    excerpts=[];links=[]
    for part in parts[1:]:
        if re.match(r'^\d+\. ',part):
            lines=part.splitlines()
            if len(lines)>=3:
                publisher=re.sub(r'^\d+\. ','',lines[0])
                excerpts.append(lines[1] if not excerpts else f'{publisher}: {lines[1]}')
                links.append(f'{publisher}: {lines[-1]}')
    if not excerpts:
        return answer
    note = ('Only one source was readable; I could not independently confirm it.'
            if len(links)==1 else 'Multiple publishers were consulted; full agreement is not automatically verified.')
    return title+'\n\n'+'\n\n'.join(excerpts)+'\n\n'+'\n'.join(links)+'\n\n'+note
