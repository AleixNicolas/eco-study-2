from otree.api import *
import random
import json
import os
import csv
import threading
from datetime import datetime, timedelta, timezone

doc = """
Phase 2: 8-Day Asynchronous Network Experiment.
Configurable via Heroku Config Vars. Manual Advancement enabled.
Supports simultaneous multi-network runs via Dynamic Load Balancing.
"""

SYSTEM_LOCK = threading.Lock()

class Constants(BaseConstants):
    name_in_url = 'phase_2'
    
    num_rounds = int(os.environ.get('NETWORK_NUM_ROUNDS', 8))
    # Note: If running 'both', this should be the TOTAL capacity (e.g. 40)
    players_per_group = int(os.environ.get('NETWORK_PLAYERS_PER_GROUP', 20))
    
    PAY_PER_ROUND = 0.40    # 2 mins @ £0.20/min
    FINAL_ROUND_PAY = 1.20  # 6 mins @ £0.20/min
    BONUS_AMOUNT = 4.00
    LOTTERY_AMOUNT = 80.00
    MAX_ALLOWED_MISSES = 1
    
    json_path = os.path.join(os.path.dirname(__file__), 'network_map.json')
    if os.path.exists(json_path):
        with open(json_path, encoding='utf-8') as f:
            NETWORK_DATA = json.load(f)
    else:
        NETWORK_DATA = {}

    csv_path = os.path.join(os.path.dirname(__file__), 'news_items.csv')
    if os.path.exists(csv_path):
        with open(csv_path, encoding='utf-8') as f:
            NEWS_ITEMS = list(csv.DictReader(f))
    else:
        NEWS_ITEMS = []

    mapping_data = os.environ.get('PARTICIPANT_MAPPING')
    if mapping_data:
        clean_data = mapping_data.replace('\xa0', ' ').replace('\u200b', '').strip()
        try:
            MAPPING = json.loads(clean_data)
        except json.JSONDecodeError as e:
            print(f"CRITICAL ERROR PARSING JSON: {e}")
            MAPPING = {}
    else:
        MAPPING = {}

    QUESTIONS = {
        'opinion_1': {'text': "To what extent do you believe the world's climate is currently changing?", 'left': "Not at all", 'right': "A great deal"},
        'opinion_2': {'text': "How likely do you think it is that climate change will lead to significant natural disasters?", 'left': "Not at all likely", 'right': "Extremely likely"},
        'opinion_3': {'text': "To what extent do you feel a personal responsibility to try to reduce climate change?", 'left': "Not at all", 'right': "A great deal"},
        'opinion_4': {'text': "To what extent do you favor or oppose increasing taxes on fossil fuels?", 'left': "Strongly Oppose", 'right': "Strongly Favor"}
    }

def calculate_deadline(round_number):
    base_time_str = os.environ.get('NETWORK_DAILY_START_HOUR_UTC', '2026-03-23T16:15:00')
    try:
        base_time = datetime.strptime(base_time_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        base_time = datetime.now(timezone.utc).replace(hour=14, minute=0, second=0, microsecond=0)
        
    test_interval = os.environ.get('NETWORK_TEST_INTERVAL_MINUTES')
    
    if test_interval:
        delta = timedelta(minutes=int(test_interval))
    else:
        delta = timedelta(days=1)
        
    return base_time + (delta * round_number)

class Subsession(BaseSubsession):
    pass

def creating_session(subsession: Subsession):
    if subsession.round_number == 1:
        mode = os.environ.get('NETWORK_MODE', 'segregated').lower()
        subsession.session.vars['network_mode'] = mode

        # --- DYNAMIC 4-QUEUE ROUTING FOR SIMULTANEOUS RUNS ---
        if mode == 'both' and Constants.NETWORK_DATA:
            seg_high, seg_low, int_high, int_low = [], [], [], []

            seg_nodes = Constants.NETWORK_DATA.get('segregated_baseline', {}).get('nodes', {})
            for n_id_str, data in seg_nodes.items():
                if data['opinion'] < 0.5: 
                    seg_high.append(int(n_id_str))
                else:
                    seg_low.append(int(n_id_str))

            int_nodes = Constants.NETWORK_DATA.get('integrated_baseline', {}).get('nodes', {})
            for n_id_str, data in int_nodes.items():
                if data['opinion'] < 0.5:
                    int_high.append(int(n_id_str))
                else:
                    int_low.append(int(n_id_str))

            subsession.session.vars['queue_seg_high'] = seg_high
            subsession.session.vars['queue_seg_low'] = seg_low
            subsession.session.vars['queue_int_high'] = int_high
            subsession.session.vars['queue_int_low'] = int_low
            
        # --- FALLBACK: SINGLE NETWORK RUNS ---
        else:
            network_size = Constants.players_per_group
            all_nodes = list(range(0, network_size))
            half = network_size // 2

            if mode == 'segregated':
                subsession.session.vars['available_high_nodes'] = list(range(0, half))
                subsession.session.vars['available_low_nodes'] = list(range(half, network_size))
            else:
                random.shuffle(all_nodes)
                subsession.session.vars['available_high_nodes'] = all_nodes[:half]
                subsession.session.vars['available_low_nodes'] = all_nodes[half:]

def vars_for_admin_report(subsession: Subsession):
    players = subsession.get_players()
    valid_players = [p for p in players if not p.participant.vars.get('screened_out', True)]
    total_players = len(valid_players)
    
    feed_lean_percentages = {}
    avg_opinion_change = {}
    sort_order = {"Far Left": 1, "Left": 2, "Lean Left": 3, "Center": 4, "Lean Right": 5, "Right": 6, "Far Right": 7, "Unknown": 8}
    
    treatments = list(set([p.participant.vars.get('network_treatment', 'segregated') for p in valid_players]))
    if not treatments:
        treatments = [os.environ.get('NETWORK_MODE', 'segregated').lower()]

    for treatment in treatments:
        t_players = [p for p in valid_players if p.participant.vars.get('network_treatment', 'segregated') == treatment]
        feed_lean_percentages[treatment] = {}
        avg_opinion_change[treatment] = {}
        
        for cat in ['High_Concern', 'Low_Concern']:
            cat_players = [p for p in t_players if p.participant.vars.get('assigned_category') == cat]
            leaning_counts = {}
            total_articles = 0
            
            for p in cat_players:
                for p_round in p.in_all_rounds():
                    feed_data = p_round.field_maybe_none('incoming_feed')
                    if feed_data:
                        try:
                            feed = json.loads(feed_data)
                            for item in feed:
                                lean = item.get('leaning', 'Unknown')
                                leaning_counts[lean] = leaning_counts.get(lean, 0) + 1
                                total_articles += 1
                        except Exception:
                            pass
                            
            lean_pcts = {}
            if total_articles > 0:
                for lean, count in leaning_counts.items():
                    lean_pcts[lean] = round((count / total_articles) * 100, 1)
            else:
                lean_pcts['No Data Yet'] = 0
                
            sorted_lean_pcts = {k: v for k, v in sorted(lean_pcts.items(), key=lambda item: sort_order.get(item[0], 99))}
            feed_lean_percentages[treatment][cat] = sorted_lean_pcts

            changes = {'opinion_1': [], 'opinion_2': [], 'opinion_3': [], 'opinion_4': []}
            for p in cat_players:
                for i in range(1, 5):
                    baseline = p.participant.vars.get(f'baseline_opinion_{i}')
                    final_opinion = None
                    for p_round in reversed(p.in_all_rounds()):
                        val = p_round.field_maybe_none(f'opinion_{i}')
                        if val is not None:
                            final_opinion = val
                            break
                    
                    if baseline is not None and final_opinion is not None:
                        try:
                            changes[f'opinion_{i}'].append(int(final_opinion) - int(baseline))
                        except ValueError:
                            pass
                            
            avg_change = {}
            for key, value_list in changes.items():
                if value_list:
                    avg_change[key] = round(sum(value_list) / len(value_list), 2)
                else:
                    avg_change[key] = "N/A"
                    
            avg_opinion_change[treatment][cat] = avg_change

    return {
        'total_players': total_players,
        'network_size': Constants.players_per_group,
        'treatments': treatments,
        'feed_lean_percentages': feed_lean_percentages,
        'avg_opinion_change': avg_opinion_change
    }

class Group(BaseGroup):
    pass

class Player(BasePlayer):
    prolific_id = models.StringField(blank=True)
    node_id = models.IntegerField(blank=True, null=True)
    category = models.StringField(blank=True) 
    network_treatment = models.StringField(blank=True)
    screened_out = models.BooleanField(initial=False)
    
    incoming_feed = models.LongStringField(initial="[]", blank=True)
    current_backlog = models.LongStringField(initial="{}", blank=True)
    outgoing_shares = models.LongStringField(initial="[]", blank=True)
    average_feed_size = models.FloatField(blank=True, null=True)
    max_feed_size = models.IntegerField(blank=True, null=True)
    average_pending_items = models.FloatField(blank=True, null=True)
    max_pending_items = models.IntegerField(blank=True, null=True)
    total_time_on_feed = models.FloatField(blank=True, null=True)
    
    participated_this_round = models.BooleanField(initial=False)
    
    opinion_1 = models.IntegerField(choices=[1, 2, 3, 4, 5], widget=widgets.RadioSelectHorizontal)
    opinion_2 = models.IntegerField(choices=[1, 2, 3, 4, 5], widget=widgets.RadioSelectHorizontal)
    opinion_3 = models.IntegerField(choices=[1, 2, 3, 4, 5], widget=widgets.RadioSelectHorizontal)
    opinion_4 = models.IntegerField(choices=[1, 2, 3, 4, 5], widget=widgets.RadioSelectHorizontal)
    
    satisfaction = models.IntegerField(choices=[1, 2, 3, 4, 5], label="Overall, how satisfied were you with your experience?", widget=widgets.RadioSelectHorizontal)
    clarity = models.IntegerField(choices=[1, 2, 3, 4, 5], label="How clear were the instructions?", widget=widgets.RadioSelectHorizontal)
    echo_chamber = models.IntegerField(choices=[1, 2, 3, 4, 5], label="To what extent do you feel the feed aligned with your own opinions?", widget=widgets.RadioSelectHorizontal)
    final_comments = models.LongStringField(label="Please include any feedback or concerns you may have.", blank=True)

def get_status_vars(player: Player):
    all_rounds = player.in_all_rounds()
    completed_total = sum([1 for p in all_rounds if p.field_maybe_none('participated_this_round') == True])
    
    past_rounds = player.in_previous_rounds()
    completed_past = sum([1 for p in past_rounds if p.field_maybe_none('participated_this_round') == True])
    
    rounds_available_past = player.round_number - 1
    missed_rounds_start = rounds_available_past - completed_past
    
    shield_active = missed_rounds_start <= 0
    chest_active = missed_rounds_start <= Constants.MAX_ALLOWED_MISSES
    
    usd_bonus_approx = Constants.BONUS_AMOUNT * 1.25
    
    return {
        'current_round': player.round_number,
        'total_rounds': Constants.num_rounds,
        'completed_total': completed_total,
        'shield_active': shield_active,
        'chest_active': chest_active,
        'bonus_amount': f"£{Constants.BONUS_AMOUNT:.2f} (approx. ${usd_bonus_approx:.2f})"
    }

# --- STANDALONE FEED GENERATOR ---
def generate_feed_for_player(player: Player):
    if player.participant.vars.get('screened_out', False):
        return

    player.category = player.participant.vars.get('assigned_category')
    player.node_id = player.participant.vars.get('node_id')
    player.prolific_id = player.participant.vars.get('prolific_id', '')

    backlog = player.participant.vars.get('backlog', {})
    shared_history = player.participant.vars.get('shared_history', set())
    
    # Check individual treatment, not the global mode
    treatment = player.participant.vars.get('network_treatment', 'segregated')
    baseline_key = f"{treatment}_baseline"
    node_str = str(player.node_id)
    node_int = player.node_id

    neighbors = []
    starting_items = []

    if baseline_key in Constants.NETWORK_DATA:
        baseline_data = Constants.NETWORK_DATA[baseline_key]
        neighbors = baseline_data.get('network', {}).get(node_str, [])
        starting_items = baseline_data.get('nodes', {}).get(node_str, {}).get('starting_items', [])
    else:
        neighbors = Constants.NETWORK_DATA.get(node_str, Constants.NETWORK_DATA.get(node_int, []))
    
    new_items = {}

    if player.round_number > 1:
        prev_subsession = player.subsession.in_round(player.round_number - 1)
        
        # --- THE FIREWALL ---
        prev_players = [p for p in prev_subsession.get_players() if p.participant.vars.get('network_treatment') == treatment]
        
        this_player_prev = next((p for p in prev_players if p.participant.vars.get('node_id') == player.node_id), None)
        if this_player_prev and this_player_prev.field_maybe_none('outgoing_shares'):
            try:
                shares = json.loads(this_player_prev.outgoing_shares)
                for item_id in shares:
                    shared_history.add(str(item_id))
            except Exception:
                pass
        player.participant.vars['shared_history'] = shared_history

        for n_id in neighbors:
            n_player = next((p for p in prev_players if p.participant.vars.get('node_id') == n_id), None)
            if n_player and n_player.field_maybe_none('outgoing_shares'):
                try:
                    n_shares = json.loads(n_player.outgoing_shares)
                    for item_id in n_shares:
                        str_id = str(item_id)
                        if str_id not in shared_history:
                            new_items[str_id] = new_items.get(str_id, 0) + 1
                except Exception:
                    pass
                    
    backlog = {str(k): v for k, v in backlog.items() if str(k) not in shared_history}
    feed_item_ids = []

    if player.round_number == 1 and starting_items:
        feed_item_ids = [str(item) for item in starting_items]
    else:
        pool_new = list(new_items.keys())
        weights_new = [new_items[k] for k in pool_new]
        
        while len(feed_item_ids) < 4 and pool_new:
            choice = random.choices(pool_new, weights=weights_new, k=1)[0]
            feed_item_ids.append(choice)
            idx = pool_new.index(choice)
            pool_new.pop(idx)
            weights_new.pop(idx)
            
        if len(feed_item_ids) < 4:
            pool_old = list(backlog.keys())
            weights_old = [backlog[k] for k in pool_old]
            while len(feed_item_ids) < 4 and pool_old:
                choice = random.choices(pool_old, weights=weights_old, k=1)[0]
                feed_item_ids.append(choice)
                idx = pool_old.index(choice)
                pool_old.pop(idx)
                weights_old.pop(idx)
        
        for k, v in new_items.items():
            backlog[str(k)] = backlog.get(str(k), 0) + v

    for item_id in feed_item_ids:
        if str(item_id) in backlog:
            del backlog[str(item_id)]

    if len(feed_item_ids) < 4:
        needed = 4 - len(feed_item_ids)
        all_ids = [str(item.get('id', '')) for item in Constants.NEWS_ITEMS]
        available_pool = [i for i in all_ids if i not in feed_item_ids and i not in shared_history and i != '']
        if available_pool:
            padding_items = random.sample(available_pool, min(needed, len(available_pool)))
            feed_item_ids.extend(padding_items)

    player.participant.vars['backlog'] = backlog
    player.current_backlog = json.dumps(backlog)

    feed_items = []
    for item_id in feed_item_ids:
        item_data = next((item for item in Constants.NEWS_ITEMS if str(item.get('id', '')) == str(item_id)), None)
        if item_data:
            feed_items.append(item_data)
            
    player.incoming_feed = json.dumps(feed_items)

# --- PAGES ---

class ArrivalGatekeeper(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        if timeout_happened:
            for p in player.in_all_rounds():
                p.screened_out = True
            player.participant.vars['screened_out'] = True
            player.participant.vars['is_ghost'] = True
            player.participant.vars['screenout_reason'] = 'timeout'
            return

        raw_label = str(player.participant.label)
        player.participant.vars['raw_label_seen'] = raw_label

        p_label = player.participant.label or f"TEST_USER_{player.id_in_group}"
        player.participant.vars['prolific_id'] = p_label
        player.participant.vars['processed_label'] = p_label
        
        for p in player.in_all_rounds():
            p.prolific_id = p_label
        
        if p_label not in Constants.MAPPING:
            for p in player.in_all_rounds():
                p.screened_out = True
            player.participant.vars['screened_out'] = True
            player.participant.vars['screenout_reason'] = 'invalid_id'
            return 

        data = Constants.MAPPING[p_label]
        cat = data.get('category')
        player.participant.vars['assigned_category'] = cat
        player.participant.vars['baseline_opinion_1'] = data.get('opinion_1')
        player.participant.vars['baseline_opinion_2'] = data.get('opinion_2')
        player.participant.vars['baseline_opinion_3'] = data.get('opinion_3')
        player.participant.vars['baseline_opinion_4'] = data.get('opinion_4')

        with SYSTEM_LOCK:
            assigned_node = None
            assigned_treatment = None
            mode = player.session.vars.get('network_mode', 'segregated')

            # --- DYNAMIC LOAD BALANCER ---
            if mode == 'both':
                if cat == 'High_Concern':
                    q_seg = player.session.vars['queue_seg_high']
                    q_int = player.session.vars['queue_int_high']
                else:
                    q_seg = player.session.vars['queue_seg_low']
                    q_int = player.session.vars['queue_int_low']

                if len(q_seg) > 0 or len(q_int) > 0:
                    if len(q_seg) >= len(q_int) and len(q_seg) > 0:
                        assigned_node = q_seg.pop(0)
                        assigned_treatment = 'segregated'
                    elif len(q_int) > 0:
                        assigned_node = q_int.pop(0)
                        assigned_treatment = 'integrated'
            else:
                assigned_treatment = mode
                if cat == 'High_Concern' and player.session.vars['available_high_nodes']:
                    assigned_node = player.session.vars['available_high_nodes'].pop(0)
                elif cat == 'Low_Concern' and player.session.vars['available_low_nodes']:
                    assigned_node = player.session.vars['available_low_nodes'].pop(0)

            if assigned_node is not None:
                for p in player.in_all_rounds():
                    p.node_id = assigned_node
                    p.category = cat
                    p.network_treatment = assigned_treatment
                    p.screened_out = False
                player.participant.vars['node_id'] = assigned_node
                player.participant.vars['network_treatment'] = assigned_treatment
                player.participant.vars['screened_out'] = False 
                player.participant.label = p_label
            else:
                for p in player.in_all_rounds():
                    p.screened_out = True
                player.participant.vars['screened_out'] = True 
                player.participant.vars['screenout_reason'] = 'network_full'
                player.participant.label = p_label

class CapacityScreenout(Page):
    @staticmethod
    def is_displayed(player: Player):
        is_screened = player.participant.vars.get('screened_out', False)
        is_ghost = player.participant.vars.get('is_ghost', False)
        return player.round_number == 1 and is_screened and not is_ghost

    @staticmethod
    def vars_for_template(player: Player):
        return {
            'screenout_reason': player.participant.vars.get('screenout_reason', 'unknown'),
            'raw_label': player.participant.vars.get('raw_label_seen', 'None'),
            'processed_label': player.participant.vars.get('processed_label', 'None'),
            'dict_keys': str(list(Constants.MAPPING.keys()))
        }

class FeedTaskGatekeeper(Page):
    @staticmethod
    def is_displayed(player: Player):
        return not player.participant.vars.get('screened_out', False)

    @staticmethod
    def vars_for_template(player: Player):
        return get_status_vars(player)

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        generate_feed_for_player(player)

class FeedTask(Page):
    form_model = 'player'
    form_fields = ['outgoing_shares', 'average_feed_size', 'max_feed_size', 'average_pending_items', 'max_pending_items', 'total_time_on_feed']
    
    @staticmethod
    def is_displayed(player: Player):
        return not player.participant.vars.get('screened_out', False)

    @staticmethod
    def vars_for_template(player: Player):
        target = calculate_deadline(player.round_number)
        vars_dict = {
            'deadline_timestamp': target.isoformat()
        }
        vars_dict.update(get_status_vars(player))
        return vars_dict

    @staticmethod
    def js_vars(player: Player):
        return {'incoming_feed': json.loads(player.field_maybe_none('incoming_feed') or "[]")}

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        if not timeout_happened:
            player.participated_this_round = True

class FinalOpinions(Page):
    form_model = 'player'
    form_fields = ['opinion_1', 'opinion_2', 'opinion_3', 'opinion_4']
    
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == Constants.num_rounds and not player.participant.vars.get('screened_out', False)

    @staticmethod
    def vars_for_template(player: Player):
        q_keys = ['opinion_1', 'opinion_2', 'opinion_3', 'opinion_4']
        questions_data = [{'name': f, 'text': Constants.QUESTIONS[f]['text'], 'left': Constants.QUESTIONS[f]['left'], 'right': Constants.QUESTIONS[f]['right']} for f in q_keys]
        vars_dict = {'questions_data': questions_data}
        vars_dict.update(get_status_vars(player))
        return vars_dict

class FinalFeedback(Page):
    form_model = 'player'
    form_fields = ['satisfaction', 'clarity', 'echo_chamber', 'final_comments']
    
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == Constants.num_rounds and not player.participant.vars.get('screened_out', False)

    @staticmethod
    def vars_for_template(player: Player):
        return get_status_vars(player)

class EndOfDayWait(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number < Constants.num_rounds and not player.participant.vars.get('screened_out', False)

    @staticmethod
    def vars_for_template(player: Player):
        codes_json = os.environ.get('PROLIFIC_DAILY_CODES', '{}')
        try:
            daily_codes = json.loads(codes_json)
        except json.JSONDecodeError:
            daily_codes = {}
            
        current_code = daily_codes.get(str(player.round_number), "MISSING_CODE")
        daily_url = f"https://app.prolific.com/submissions/complete?cc={current_code}"
        target = calculate_deadline(player.round_number)
            
        vars_dict = {
            'prolific_daily_url': daily_url,
            'next_round_timestamp': target.isoformat()
        }
        vars_dict.update(get_status_vars(player))
        return vars_dict

class CompletionRedirect(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == Constants.num_rounds and not player.participant.vars.get('screened_out', False)

    @staticmethod
    def vars_for_template(player: Player):
        all_rounds = player.in_all_rounds()
        completed_rounds = sum([1 for p in all_rounds if p.field_maybe_none('participated_this_round') == True])
        missed_rounds = Constants.num_rounds - completed_rounds
        
        final_base_pay = Constants.FINAL_ROUND_PAY if player.participated_this_round else 0.00
        bonus = Constants.BONUS_AMOUNT if missed_rounds <= Constants.MAX_ALLOWED_MISSES else 0.00
        total_final_payment = final_base_pay + bonus
        
        lottery_eligible = (missed_rounds == 0)
        
        codes_json = os.environ.get('PROLIFIC_DAILY_CODES', '{}')
        try:
            daily_codes = json.loads(codes_json)
        except json.JSONDecodeError:
            daily_codes = {}
        
        current_code = daily_codes.get(str(player.round_number), "MISSING_CODE")
        completion_url = f"https://app.prolific.com/submissions/complete?cc={current_code}"
        
        usd_base_approx = final_base_pay * 1.25
        usd_bonus_approx = bonus * 1.25
        usd_total_approx = total_final_payment * 1.25
        
        vars_dict = {
            'completed_rounds': completed_rounds,
            'final_base_pay': f"£{final_base_pay:.2f} (approx. ${usd_base_approx:.2f})",
            'final_bonus_amount': f"£{bonus:.2f} (approx. ${usd_bonus_approx:.2f})",
            'total_final_payment': f"£{total_final_payment:.2f} (approx. ${usd_total_approx:.2f})",
            'earned_bonus': bonus > 0,
            'lottery_eligible': lottery_eligible,
            'completion_url': completion_url,
            'lottery_ticket': player.participant.code.upper()
        }
        vars_dict.update(get_status_vars(player))
        return vars_dict

page_sequence = [
    ArrivalGatekeeper, 
    CapacityScreenout, 
    FeedTaskGatekeeper, 
    FeedTask, 
    FinalOpinions, 
    FinalFeedback, 
    EndOfDayWait, 
    CompletionRedirect
]