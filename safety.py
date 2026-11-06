"""Basic request and source filters for an educational bot, not a complete moderator."""
import re


def request_filter(message):
    text = ' '.join(message.lower().split())
    if re.search(r'как\s+(?:сделать|собрать|изготовить).{0,30}(?:бомб|взрывное устройство)|как.{0,30}(?:украсть парол|взломать аккаунт|отравить человека)',text):
        return 'Я не помогу с инструкциями причинить вред или украсть аккаунт. Могу объяснить безопасность.'
    if re.search(r'(?:хочу|планирую|как).{0,20}(?:убить себя|покончить с собой)',text):
        return 'Спасибо, что рассказал. Пожалуйста, обратись к взрослому, которому доверяешь, или к человеку рядом. При непосредственной опасности свяжись с местными экстренными службами.'
    if re.search(r'какую дозу|сколько таблеток|поставь диагноз|какое лекарство мне',text):
        return 'Я не могу выбирать лекарства или ставить диагноз. Обратись к врачу и взрослому, которому доверяешь.'
    if re.search(r'(?:пришли|покажи|найди|создай).{0,30}(?:порно|порнограф|обнажён)',text):
        return 'Я не помогу искать откровенные сексуальные материалы. Могу помочь с подходящими по возрасту вопросами о здоровье.'
    if re.search(r'мой (?:пароль|секретный токен)\s*(?:это|:|=)',text):
        return 'Это похоже на секретные данные. Не отправляй их; замени секрет, если он стал известен другим.'
    if len(message) > 1000:
        return 'Please send a shorter message, under 1,000 characters.'
    if re.search(r'\b\d{8,}:[A-Za-z0-9_-]{25,}\b', message) or re.search(r'\bmy (?:password|secret token|api key) (?:is|=)', text):
        return 'That looks like a private credential. Do not share it. Replace it if it was exposed.'
    if re.search(r'\b(?:i want to|i will|how (?:can|do) i|help me)\s+(?:kill myself|hurt myself|end my life)\b', text):
        return 'I am glad you told me. Please contact a trusted adult or someone nearby now. If you are in immediate danger, contact local emergency services.'
    if re.search(r'\b(?:make|build|assemble)\b.{0,35}\b(?:bomb|explosive device)\b', text) or re.search(r'\b(?:how to|help me)\b.{0,35}\b(?:poison someone|kill someone|steal passwords|hack an account|create ransomware)\b',text):
        return 'I cannot help with instructions to hurt people or steal accounts. I can explain safety or defensive security instead.'
    if re.search(r'\b(?:show|send|find|generate|write|create)\b.{0,40}\b(?:porn|pornography|nudes|explicit sexual|erotic story)\b',text):
        return 'I cannot help find explicit sexual material. I can help with age-appropriate health or relationship questions.'
    if re.search(r'\b(?:what dose|how much medicine|diagnose me)\b|\bshould i take\b.{0,30}\b(?:medicine|medication|pills|tablets|mg)\b',text):
        return 'I cannot choose medicine or diagnose you. Ask a qualified health professional and a trusted adult.'
    return None


def safe_source_text(text):
    # Never relay common credential-harvesting or instruction-injection phrases.
    if re.search(r'ignore (?:all |the )?(?:previous|prior) instructions|reveal (?:your |the )?(?:token|password)|send (?:me |us )?your (?:password|api key)', text, re.I):
        return False
    return request_filter(text) is None
