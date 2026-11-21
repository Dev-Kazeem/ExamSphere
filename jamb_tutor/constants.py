"""Fixed values shared across the app. No Django imports, so they are easy to test."""

JAMB_MAX_SCORE = 400

# Mock exam rules
MOCK_QUESTIONS = 20
MOCK_SECONDS = 30 * 60
MOCK_MIN_QUESTIONS = 5          # a subject needs at least this many questions before a mock can start
MOCK_GRACE_SECONDS = 45         # allowance for slow networks when the timer auto-submits
WHATSAPP_MOCK_QUESTIONS = 10

# (short name, slug, full name, bootstrap icon)
SUBJECTS = [
    ('English', 'english', 'Use of English', 'bi-chat-quote'),
    ('Maths', 'maths', 'Mathematics', 'bi-calculator'),
    ('Physics', 'physics', 'Physics', 'bi-lightning-charge'),
    ('Chemistry', 'chemistry', 'Chemistry', 'bi-droplet'),
    ('Biology', 'biology', 'Biology', 'bi-flower1'),
    ('Economics', 'economics', 'Economics', 'bi-graph-up-arrow'),
    ('Government', 'government', 'Government', 'bi-bank'),
    ('IRS', 'irs', 'Islamic Religious Studies', 'bi-moon-stars'),
    ('CRS', 'crs', 'Christian Religious Studies', 'bi-book'),
]
SUBJECT_NAMES = [s[0] for s in SUBJECTS]

SUBJECT_ALIASES = {
    'english': 'English', 'use of english': 'English', 'english language': 'English',
    'maths': 'Maths', 'math': 'Maths', 'mathematics': 'Maths',
    'physics': 'Physics', 'physic': 'Physics',
    'chemistry': 'Chemistry', 'chem': 'Chemistry',
    'biology': 'Biology', 'bio': 'Biology',
    'economics': 'Economics', 'economic': 'Economics', 'econs': 'Economics',
    'government': 'Government', 'govt': 'Government', 'gov': 'Government',
    'irs': 'IRS', 'islamic religious studies': 'IRS', 'islamic studies': 'IRS',
    'crs': 'CRS', 'crk': 'CRS', 'christian religious studies': 'CRS',
    'christian religious knowledge': 'CRS',
}

# Subjects highlighted for each combination (English is compulsory in JAMB).
COMBINATIONS = {
    'science': ['English', 'Maths', 'Physics', 'Chemistry', 'Biology'],
    'art': ['English', 'Government', 'CRS', 'IRS', 'Economics'],
    'commercial': ['English', 'Maths', 'Economics', 'Government'],
}

LANGUAGE_LABELS = {'pidgin': 'Pidgin', 'english': 'English', 'hausa': 'Hausa'}

CSV_COLUMNS = [
    'subject', 'topic', 'question_text', 'option_a', 'option_b', 'option_c', 'option_d',
    'correct_option', 'explanation', 'year',
]
