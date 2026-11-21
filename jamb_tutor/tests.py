"""
Run with:  python manage.py test jamb_tutor

These cover the pure logic (phone numbers, CSV and AI-output parsing, WhatsApp signature and
commands, streaks, scoring). They need no database.
"""
import hashlib
import hmac
from datetime import date, timedelta

from django.test import SimpleTestCase

from . import logic as L


class PhoneAndNameTests(SimpleTestCase):
    def test_valid_phones_become_whatsapp_format(self):
        for raw, want in [("08031234567", "2348031234567"), ("+234 803 123 4567", "2348031234567"),
                          ("8031234567", "2348031234567"), ("2348031234567", "2348031234567"),
                          ("0903-123-4567", "2349031234567"), ("00234 70 1234 5678", "2347012345678")]:
            self.assertEqual(L.normalize_phone(raw), want)

    def test_bad_phones_are_rejected(self):
        for bad in ["", "0803", "02031234567", "12345678901", "abc", "+1 415 555 2671"]:
            with self.assertRaises(ValueError, msg=bad):
                L.normalize_phone(bad)

    def test_split_full_name(self):
        self.assertEqual(L.split_full_name("Amina Bello Yusuf"), ("Amina", "Bello Yusuf"))
        self.assertEqual(L.split_full_name("  Tunde "), ("Tunde", ""))
        self.assertEqual(L.split_full_name(""), ("", ""))


class SubjectAndDuplicateTests(SimpleTestCase):
    def test_subject_aliases(self):
        self.assertEqual(L.resolve_subject("Mathematics"), "Maths")
        self.assertEqual(L.resolve_subject("PHYSIC"), "Physics")
        self.assertEqual(L.resolve_subject("Christian Religious Studies"), "CRS")
        self.assertEqual(L.resolve_subject("Govt."), "Government")
        self.assertIsNone(L.resolve_subject("Literature"))

    def test_whatsapp_subject_choice(self):
        self.assertEqual(L.resolve_subject_choice("2"), "Maths")
        self.assertEqual(L.resolve_subject_choice("9"), "CRS")
        self.assertIsNone(L.resolve_subject_choice("10"))
        self.assertEqual(L.resolve_subject_choice("irs"), "IRS")

    def test_duplicate_hash_ignores_case_spacing_and_punctuation(self):
        self.assertEqual(L.question_hash(1, "Capital of Nigeria?"), L.question_hash(1, "  capital   of nigeria "))
        self.assertNotEqual(L.question_hash(1, "What is 2 + 2?"), L.question_hash(2, "What is 2 + 2?"))


class ScoreAndStreakTests(SimpleTestCase):
    def test_scores(self):
        self.assertEqual(L.percentage(16, 20), 80.0)
        self.assertEqual(L.projected_score(16, 20), 320)
        self.assertEqual(L.projected_score(0, 0), 0)

    def test_streaks(self):
        today = date(2026, 11, 20)
        self.assertEqual(L.next_streak(None, 0, today), (1, today))
        self.assertEqual(L.next_streak(today - timedelta(days=1), 4, today), (5, today))
        self.assertEqual(L.next_streak(today - timedelta(days=3), 9, today), (1, today))
        self.assertEqual(L.next_streak(today, 7, today), (7, today))
        self.assertEqual(L.current_streak(today - timedelta(days=1), 4, today), 4)
        self.assertEqual(L.current_streak(today - timedelta(days=2), 4, today), 0)
        self.assertEqual(L.current_streak(None, 0, today), 0)

    def test_greetings(self):
        self.assertEqual(L.greeting_for("Ada", "english", 9), "Good morning, Ada")
        self.assertEqual(L.greeting_for("Ada", "english", 18), "Good evening, Ada")
        self.assertTrue(L.greeting_for("Ada", "pidgin", 9).startswith("How far"))
        self.assertTrue(L.greeting_for("Ada", "hausa", 9).startswith("Sannu"))


class RowCleaningTests(SimpleTestCase):
    good = dict(subject="mathematics", topic="Algebra", question_text="Solve 2x = 10", option_a="2",
                option_b="5", option_c="10", option_d="20", correct_option="b", explanation="x = 5", year="2019")

    def test_good_row(self):
        row, error = L.clean_question_row(self.good)
        self.assertEqual(error, "")
        self.assertEqual((row["subject"], row["correct_option"], row["year"]), ("Maths", "B", "2019"))

    def test_ways_of_writing_the_answer(self):
        for spelled, want in [("Option C", "C"), ("(d)", "D"), ("Answer: A", "A"), ("5", "B")]:
            row, error = L.clean_question_row({**self.good, "correct_option": spelled})
            self.assertEqual((row["correct_option"], error), (want, ""))

    def test_problems_are_reported(self):
        cases = [({"subject": "Literature"}, "Unknown subject"), ({"option_c": ""}, "Option C is empty"),
                 ({"correct_option": "E"}, "Correct option"), ({"year": "abcd"}, "Year"),
                 ({"year": "1850"}, "Year"), ({"option_a": "x" * 501}, "longer than")]
        for change, expected in cases:
            _, error = L.clean_question_row({**self.good, **change})
            self.assertIn(expected, error)

    def test_defaults(self):
        row, error = L.clean_question_row({**self.good, "subject": "", "year": ""}, "Physics", 2020)
        self.assertEqual((error, row["subject"], row["year"]), ("", "Physics", "2020"))
        self.assertEqual(L.clean_question_row({**self.good, "topic": ""})[0]["topic"], "General")


class CsvTests(SimpleTestCase):
    def test_parse_with_bom_blank_and_bad_rows(self):
        text = ("\ufeffSubject,Topic,Question_Text,Option_A,Option_B,Option_C,Option_D,Correct_Option,Explanation,Year\r\n"
                "Maths,Algebra,Solve 2x = 10,2,5,10,20,B,x = 5,2019\r\n"
                "Physic,Motion,What is the unit of force?,Joule,Newton,Watt,Pascal,B,,\r\n"
                ",,,,,,,,,\r\n"
                "Literature,Poetry,Who wrote Things Fall Apart?,A,B,C,D,A,,\r\n"
                "Biology,Cells,The powerhouse of the cell is,Nucleus,Ribosome,,Mitochondrion,D,,\r\n")
        rows, problems = L.parse_question_csv(text.encode("utf-8"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["subject"], "Physics")
        self.assertEqual([p[0] for p in problems], [5, 6])          # row numbers match the spreadsheet
        self.assertIn("Unknown subject", problems[0][1])
        self.assertIn("Option C is empty", problems[1][1])

    def test_file_level_errors(self):
        for bad, expected in [(b"", "empty"), (b"a,b\r\n1,2\r\n", "missing required")]:
            with self.assertRaises(L.FileProblem) as ctx:
                L.parse_question_csv(bad)
            self.assertIn(expected, str(ctx.exception))

    def test_latin1_csv(self):
        data = "subject,topic,question_text,option_a,option_b,option_c,option_d,correct_option\r\nEnglish,Vocab,Caf\xe9 means,a,b,c,d,A\r\n"
        self.assertEqual(L.parse_question_csv(data.encode("latin-1"))[0][0]["question_text"], "Caf\xe9 means")


class AiOutputTests(SimpleTestCase):
    good = '[{"question_text":"Q1 long enough","option_a":"a"},{"question_text":"Q2 long enough"}]'

    def test_tolerates_wrapping(self):
        for text in [self.good, "```json\n" + self.good + "\n```", "Here you go:\n" + self.good + "\nHope that helps",
                     '{"questions": ' + self.good + '}']:
            self.assertEqual(len(L.parse_json_array(text)), 2)

    def test_truncated_reply_keeps_complete_items(self):
        cut = ('[{"question_text":"Q1 long enough","option_a":"a"},{"question_text":"Q2 long enough","option_a":"b"},'
               '{"question_text":"Q3 cut o')
        self.assertEqual(len(L.parse_json_array(cut)), 2)

    def test_garbage_is_rejected(self):
        for bad in ["", "no json here", "{}", '"just a string"']:
            with self.assertRaises(ValueError, msg=bad):
                L.parse_json_array(bad)

    def test_chunking(self):
        text = "\n".join(f"Line {i} " + "x" * 40 for i in range(200))
        chunks = L.split_text_chunks(text, max_chars=1000)
        self.assertTrue(all(len(c) <= 1000 for c in chunks))
        self.assertEqual("\n".join(chunks).count("Line"), 200)
        self.assertEqual(L.split_text_chunks(""), [])
        self.assertEqual([len(c) for c in L.split_text_chunks("y" * 2500, 1000)], [1000, 1000, 500])


class WhatsAppTests(SimpleTestCase):
    def test_signature(self):
        body, secret = b'{"entry":[]}', "s3cret"
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertTrue(L.verify_signature(body, sig, secret))
        self.assertFalse(L.verify_signature(body + b" ", sig, secret))      # tampered
        self.assertFalse(L.verify_signature(body, sig, "other"))
        self.assertFalse(L.verify_signature(body, "", secret))
        self.assertFalse(L.verify_signature(body, sig, ""))                  # fails closed without a secret

    def test_payload(self):
        payload = {"entry": [{"changes": [{"value": {"messages": [
            {"id": "wamid.1", "from": "2348031234567", "type": "text", "text": {"body": "  Mock maths "}},
            {"id": "wamid.2", "from": "2348031234567", "type": "image"},
            {"id": "wamid.3", "from": "2349031234567", "type": "button", "button": {"text": "A"}}]}}]}]}
        messages = L.extract_messages(payload)
        self.assertEqual([m["text"] for m in messages], ["Mock maths", "", "A"])
        self.assertEqual(L.extract_messages({}), [])
        self.assertEqual(L.extract_messages({"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]}), [])

    def test_commands(self):
        for text, want in [("start", ("start", "")), ("Hi!", ("start", "")), (" MOCK ", ("mock", "")),
                           ("Mock Maths", ("mock", "maths")), ("STOP", ("stop", "")),
                           ("subscribe", ("subscribe", "")), ("what is photosynthesis", ("", "")),
                           ("mockery is a word", ("", "")), ("", ("", ""))]:
            self.assertEqual(L.parse_command(text), want, text)

    def test_answer_letters(self):
        for text, want in [("A", "A"), ("b", "B"), (" (c) ", "C"), ("d.", "D"), ("option b", "B"),
                           ("E", ""), ("ab", ""), ("answer is a", "")]:
            self.assertEqual(L.parse_answer_letter(text), want, text)

    def test_long_messages_are_split(self):
        long_text = "\n\n".join(f"Paragraph {i}: " + "w" * 300 for i in range(30))
        parts = L.split_message(long_text, limit=1000)
        self.assertTrue(all(len(p) <= 1000 for p in parts))
        self.assertEqual("".join(parts).count("Paragraph"), 30)
        self.assertEqual(L.split_message("hello"), ["hello"])
        self.assertEqual(L.split_message("   "), [])

    def test_text_and_prompt(self):
        self.assertIn("Amina", L.welcome_text("Amina", "pidgin"))
        self.assertTrue(L.welcome_text("Amina", "klingon").startswith("Hello Amina"))
        self.assertEqual(L.subject_menu().splitlines()[1], "2. Mathematics")
        prompt = L.build_teacher_prompt("Amina", "pidgin", "science", "UNILAG", 280, "whatsapp")
        for fragment in ("Pidgin", "UNILAG", "280/400", "180 words", "ONE practical question"):
            self.assertIn(fragment, prompt)
