import os, requests
from .models import WhatsAppSession, JambQuestion
from .ai_helper import ask_jamb_ai

TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")

def send_whatsapp(to, text):
    url = f"https://graph.facebook.com/v21.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text[:3900]}}
    try: requests.post(url, headers=headers, json=data, timeout=10)
    except Exception as e: print(e)

def get_session(phone):
    s, _ = WhatsAppSession.objects.get_or_create(phone=phone)
    return s

def handle_whatsapp(phone, text, name=""):
    text = text.strip()
    s = get_session(phone)
    if name: s.name = name; s.save()
    low = text.lower()

    if low in ["hi","hello","start","menu","help"]:
        send_whatsapp(phone, f"Welcome {s.name or 'My guy'}! 🎓\n\nType:\nDRILL - Practice JAMB question\nASK <your question> - Ask AI Teacher\nLANG PIDGIN / LANG HAUSA / LANG ENGLISH - Change language\nSCORE - See your score")
        return
    if low.startswith("lang "):
        lang = text[5:].strip().capitalize()
        if lang in ["Pidgin","Hausa","English"]:
            s.language = lang; s.save()
            send_whatsapp(phone, f"Done! I go teach you in {lang} now. Type DRILL")
        return
    if low == "score":
        send_whatsapp(phone, f"Your score: {s.score}/{s.questions_answered} correct. Keep am up! Type DRILL")
        return
    if low == "drill":
        q = JambQuestion.objects.order_by('?').first()
        if not q: send_whatsapp(phone, "No questions yet. Type ASK to ask AI."); return
        s.current_q_id = q.id; s.state="drilling"; s.save()
        send_whatsapp(phone, f"📝 {q.subject} - {q.topic}\n\n{q.question_text}\n\nA. {q.option_a}\nB. {q.option_b}\nC. {q.option_c}\nD. {q.option_d}\n\nReply A, B, C or D")
        return
    if low in ["a","b","c","d"] and s.state=="drilling" and s.current_q_id:
        q = JambQuestion.objects.get(id=s.current_q_id)
        s.questions_answered += 1
        if low.upper() == q.correct_option:
            s.score += 1; s.save()
            send_whatsapp(phone, f"✅ Correct! {q.explanation}\n\nYour score: {s.score}/{s.questions_answered}\nType DRILL for next one")
        else:
            s.save()
            send_whatsapp(phone, f"❌ No be {low.upper()}. Correct na {q.correct_option}. {q.explanation}\n\nType DRILL for next")
        s.state="idle"; s.save()
        return
    if low.startswith("ask "):
        question = text[4:]
        send_whatsapp(phone, "I dey think... wait small ⏳")
        answer = ask_jamb_ai(question, language=s.language, student_name=s.name or "Student")
        send_whatsapp(phone, answer)
        return
    send_whatsapp(phone, "I no understand. Type DRILL to practice or ASK <question> to ask me. Type MENU for help")