from os import environ

# --- REQUIRED SECURITY SETTINGS ---
# This looks for OTREE_SECRET_KEY in your Heroku Config Vars
SECRET_KEY = environ.get('OTREE_SECRET_KEY')

SESSION_CONFIGS = [
    dict(
        name='phase2_main_network',
        display_name="Phase 2: 7-Day Network Experiment",
        app_sequence=['phase_2'],
        num_demo_participants=20,
        completion_url='https://app.prolific.com/submissions/complete?cc=YOUR_FINAL_CODE',
    ),
]

SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.00, 
    participation_fee=0.00, 
    doc=""
)

PARTICIPANT_FIELDS = [
    'prolific_id',
    'node_id',
    'assigned_category',
    'baseline_opinion_1',
    'baseline_opinion_2',
    'baseline_opinion_3',
    'baseline_opinion_4',
    'backlog'
]

SESSION_FIELDS = []

ROOMS = [
    dict(name='main_network_room', display_name='Main 20-Node Network Room'),
]

LANGUAGE_CODE = 'en'
REAL_WORLD_CURRENCY_CODE = 'USD'
USE_POINTS = True

# --- ADMIN ACCESS ---
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD', 'password')

# --- OTREE SETUP ---
DEMO_PAGE_INTRO_HTML = """ """
DEBUG = environ.get('OTREE_PRODUCTION') is None