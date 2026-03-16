from os import environ

# --- REQUIRED SECURITY SETTINGS ---
SECRET_KEY = environ.get('OTREE_SECRET_KEY', '2003881942849')

SESSION_CONFIGS = [
    # Removed the phase_1 config block from here!
    dict(
        name='phase2_main_network',
        display_name="Phase 2: 7-Day Network Experiment",
        app_sequence=['phase_2'],
        num_demo_participants=20,
        completion_url='https://app.prolific.com/submissions/complete?cc=YOUR_FINAL_CODE',
        start_date="Monday, October 16th", 
        daily_start_hour_utc=14, # 14:00 UTC
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
    dict(name='testing_room', display_name='Automated Testing Room'),
    dict(name='main_network_room', display_name='Main 20-Node Network Room'),
]

LANGUAGE_CODE = 'en'
REAL_WORLD_CURRENCY_CODE = 'USD'
USE_POINTS = True

# --- ADMIN ACCESS ---
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD', 'password')

DEMO_PAGE_INTRO_HTML = """ """
DEBUG = environ.get('OTREE_PRODUCTION') is None