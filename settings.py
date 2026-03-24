from os import environ

SECRET_KEY = environ.get('OTREE_SECRET_KEY', '2003881942849')

SESSION_CONFIGS = [
    dict(
        name='phase2_main_network',
        display_name="Phase 2: 8-Day Network Experiment",
        app_sequence=['phase_2'],
        # Dynamically pull the room size, default to 40 if not set
        num_demo_participants=int(environ.get('NETWORK_DEMO_PARTICIPANTS', 40)),
        completion_url='https://app.prolific.com/submissions/complete?cc=FINAL_BONUS_CODE',
    ),
]

SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.00, participation_fee=0.00, doc=""
)

PARTICIPANT_FIELDS = [
    'prolific_id', 'node_id', 'assigned_category', 'baseline_opinion_1',
    'baseline_opinion_2', 'baseline_opinion_3', 'baseline_opinion_4', 'backlog',
    'screened_out', 'is_ghost'
]
SESSION_FIELDS = []

ROOMS = [
    dict(name='main_network_room', display_name='Main Network Room'),
]

LANGUAGE_CODE = 'en'
REAL_WORLD_CURRENCY_CODE = 'USD'
USE_POINTS = True
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD', 'password')