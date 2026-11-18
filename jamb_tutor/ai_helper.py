import os, google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")

def ask_jamb_ai(question, language="Pidgin", subject="General", student_name="Student"):
    prompt = f"""
    You are a friendly JAMB tutor for Nigerian Science student.
    Student: {student_name}. Subject: {subject}. Wants 280+ in JAMB.
    QUESTION: {question}
    ANSWER IN: {language}
    RULES:
    1. Answer in {language}. Pidgin = Nigerian Pidgin. Hausa = simple Hausa. English = very simple.
    2. Use Nigerian example: market, farming in Jos, football, mama put.
    3. Structure:
       - Direct answer in 1 sentence
       - WHY - 3 short steps
       - EXAM TRICK - how JAMB sets it
       - 1 Practice Question
    4. Max 200 words. Max 2 emojis.
    5. End with: "You understand? Type DRILL to practice"
    """
    try:
        return model.generate_content(prompt).text
    except Exception as e:
        print(f"Gemini Error: {e}")
        return "Sorry network wahala. Try again in 1 min. Type DRILL to practice while I fix am."