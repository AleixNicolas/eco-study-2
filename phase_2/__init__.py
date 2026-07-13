from otree.api import *
import random
import json
import os
import csv
import threading
from datetime import datetime, timedelta, timezone

doc = """
Phase 2: Dual-Topic (Climate & Immigration) 8-Day Asynchronous Network Experiment.
Features: User-level counterbalancing, dual-node topologies, and strict atomic queuing.
"""

SYSTEM_LOCK = threading.Lock()

class Constants(BaseConstants):
    name_in_url = 'phase_2'
    
    num_rounds = int(os.environ.get('NETWORK_NUM_ROUNDS', 8))
    players_per_group = int(os.environ.get('NETWORK_PLAYERS_PER_GROUP', 20))
    
    PAY_PER_ROUND = 0.40
    FINAL_ROUND_PAY = 0.80
    BONUS_AMOUNT = 4.00
    LOTTERY_AMOUNT = 80.00
    MAX_ALLOWED_MISSES = 1
    
    json_path = os.path.join(os.path.dirname(__file__), 'network_map.json')
    if os.path.exists(json_path):
        with open(json_path, encoding='utf-8') as f:
            NETWORK_DATA = json.load(f)
    else:
        NETWORK_DATA = {}

    def load_news(filename):
        path = os.path.join(os.path.dirname(__file__), filename)
        items = []
        if os.path.exists(path):
            with open(path, encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    items.append({str(k).strip().lower() if k else k: v for k, v in row.items()})
        return items

    CLIMATE_NEWS = load_news('news_climate.csv')
    IMM_NEWS = load_news('news_immigration.csv')

    mapping_data = os.environ.get('PARTICIPANT_MAPPING')
    if mapping_data:
        clean_data = mapping_data.replace('\xa0', ' ').replace('\u200b', '').strip()
        try:
            MAPPING = json.loads(clean_data)
        except json.JSONDecodeError:
            MAPPING = {}
    else:
        MAPPING = {}

    QUESTIONS = { 
        'climate_opinion_1': {'text': "To what extent do you favor transitioning away from fossil fuels?", 'left': "Strongly Oppose", 'right': "Strongly Favor"}, 
        'climate_opinion_2': {'text': "To what extent do you favor increasing taxes on fossil fuels?", 'left': "Strongly Oppose", 'right': "Strongly Favor"}, 
        'imm_opinion_1': {'text': "To what extent do you favor increasing the number of legal immigrants allowed?", 'left': "Strongly Oppose", 'right': "Strongly Favor"}, 
        'imm_opinion_2': {'text': "To what extent do you favor providing a path to citizenship for undocumented immigrants?", 'left': "Strongly Oppose", 'right': "Strongly Favor"} 
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
        
        network_size = Constants.players_per_group
        half = network_size // 2

        subsession.session.vars['queues'] = {
            'segregated': {'climate_L': [], 'climate_R': [], 'imm_L': [], 'imm_R': []},
            'integrated': {'climate_L': [], 'climate_R': [], 'imm_L': [], 'imm_R': []}
        }

        if mode in ['both', 'segregated']:
            subsession.session.vars['queues']['segregated']['climate_L'] = list(range(0, half))
            subsession.session.vars['queues']['segregated']['climate_R'] = list(range(half, network_size))
            subsession.session.vars['queues']['segregated']['imm_L'] = list(range(0, half))
            subsession.session.vars['queues']['segregated']['imm_R'] = list(range(half, network_size))
            
        if mode in ['both', 'integrated']:
            subsession.session.vars['queues']['integrated']['climate_L'] = list(range(0, half))
            subsession.session.vars['queues']['integrated']['climate_R'] = list(range(half, network_size))
            subsession.session.vars['queues']['integrated']['imm_L'] = list(range(0, half))
            subsession.session.vars['queues']['integrated']['imm_R'] = list(range(half, network_size))
            
            for q_key in subsession.session.vars['queues']['integrated']:
                random.shuffle(subsession.session.vars['queues']['integrated'][q_key])

def vars_for_admin_report(subsession: Subsession):
    players = subsession.get_players()
    valid_players = [p for p in players if not p.participant.vars.get('screened_out', True)]
    total_players = len(valid_players)
    
    feed_lean_percentages = {'climate': {}, 'imm': {}}
    avg_opinion_change = {'climate': {}, 'imm': {}}
    sort_order = {"Far Left": 1, "Left": 2, "Lean Left": 3, "Center": 4, "Lean Right": 5, "Right": 6, "Far Right": 7, "Unknown": 8}
    
    treatments = list(set([p.participant.vars.get('network_treatment', 'segregated') for p in valid_players]))
    if not treatments:
        treatments = [os.environ.get('NETWORK_MODE', 'segregated').lower()]

    for treatment in treatments:
        t_players = [p for p in valid_players if p.participant.vars.get('network_treatment', 'segregated') == treatment]
        
        for topic in ['climate', 'imm']:
            feed_lean_percentages[topic][treatment] = {}
            avg_opinion_change[topic][treatment] = {}
            
            for cat in ['LL', 'LR', 'RL', 'RR']:
                cat_players = [p for p in t_players if p.participant.vars.get('assigned_category') == cat]
                leaning_counts = {}
                total_articles = 0
                
                for p in cat_players:
                    for p_round in p.in_all_rounds():
                        feed_data = p_round.field_maybe_none(f'{topic}_incoming_feed')
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
                feed_lean_percentages[topic][treatment][cat] = sorted_lean_pcts

                changes = {'opinion_1': [], 'opinion_2': []}
                for p in cat_players:
                    for i in range(1, 3):
                        baseline = p.participant.vars.get(f'baseline_{topic}_opinion_{i}')
                        final_opinion = None
                        for p_round in reversed(p.in_all_rounds()):
                            val = p_round.field_maybe_none(f'{topic}_opinion_{i}')
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
                        
                avg_opinion_change[topic][treatment][cat] = avg_change

    return {
        'total_players': total_players,
        'treatments': treatments,
        'feed_lean_percentages': feed_lean_percentages,
        'avg_opinion_change': avg_opinion_change
    }

class Group(BaseGroup):
    pass

class Player(BasePlayer):
    prolific_id = models.StringField(blank=True)
    category = models.StringField(blank=True) 
    network_treatment = models.StringField(blank=True)
    topic_order = models.StringField(blank=True)
    screened_out = models.BooleanField(initial=False)
    participated_this_round = models.BooleanField(initial=False)
    
    climate_node_id = models.IntegerField(blank=True, null=True)
    imm_node_id = models.IntegerField(blank=True, null=True)
    
    climate_incoming_feed = models.LongStringField(initial="[]", blank=True)
    climate_current_backlog = models.LongStringField(initial="{}", blank=True)
    climate_outgoing_shares = models.LongStringField(initial="[]", blank=True)
    climate_average_feed_size = models.FloatField(blank=True, null=True)
    climate_max_feed_size = models.IntegerField(blank=True, null=True)
    climate_average_pending_items = models.FloatField(blank=True, null=True)
    climate_max_pending_items = models.IntegerField(blank=True, null=True)
    climate_total_time_on_feed = models.FloatField(blank=True, null=True)
    
    imm_incoming_feed = models.LongStringField(initial="[]", blank=True)
    imm_current_backlog = models.LongStringField(initial="{}", blank=True)
    imm_outgoing_shares = models.LongStringField(initial="[]", blank=True)
    imm_average_feed_size = models.FloatField(blank=True, null=True)
    imm_max_feed_size = models.IntegerField(blank=True, null=True)
    imm_average_pending_items = models.FloatField(blank=True, null=True)
    imm_max_pending_items = models.IntegerField(blank=True, null=True)
    imm_total_time_on_feed = models.FloatField(blank=True, null=True)
    
    climate_opinion_1 = models.IntegerField(choices=[1, 2, 3, 4, 5], widget=widgets.RadioSelectHorizontal)
    climate_opinion_2 = models.IntegerField(choices=[1, 2, 3, 4, 5], widget=widgets.RadioSelectHorizontal)
    imm_opinion_1 = models.IntegerField(choices=[1, 2, 3, 4, 5], widget=widgets.RadioSelectHorizontal)
    imm_opinion_2 = models.IntegerField(choices=[1, 2, 3, 4, 5], widget=widgets.RadioSelectHorizontal)
    
    satisfaction = models.IntegerField(choices=[1, 2, 3, 4, 5], label="Overall, how satisfied were you with your experience?", widget=widgets.RadioSelectHorizontal)
    clarity = models.IntegerField(choices=[1, 2, 3, 4, 5], label="How clear were the instructions?", widget=widgets.RadioSelectHorizontal)
    echo_chamber = models.IntegerField(choices=[1, 2, 3, 4, 5], label="To what extent do you feel the feeds aligned with your own opinions?", widget=widgets.RadioSelectHorizontal)
    final_comments = models.LongStringField(label="Please include any feedback or concerns you may have.", blank=True)

def get_status_vars(player: Player):
    all_rounds = player.in_all_rounds()
    completed_total = sum([1 for p in all_rounds if p.field_maybe_none('participated_this_round') == True])
    past_rounds = player.in_previous_rounds()
    completed_past = sum([1 for p in past_rounds if p.field_maybe_none('participated_this_round') == True])
    missed_rounds_start = (player.round_number - 1) - completed_past
    
    usd_bonus_approx = Constants.BONUS_AMOUNT * 1.25
    return {
        'current_round': player.round_number,
        'total_rounds': Constants.num_rounds,
        'completed_total': completed_total,
        'shield_active': missed_rounds_start <= 0,
        'chest_active': missed_rounds_start <= Constants.MAX_ALLOWED_MISSES,
        'bonus_amount': f"£{Constants.BONUS_AMOUNT:.2f} (approx. ${usd_bonus_approx:.2f})"
    }

def build_topic_feed(player: Player, topic_prefix: str, news_db: list):
    treatment = player.participant.vars.get('network_treatment', 'segregated')
    baseline_key = f"{treatment}_baseline"
    node_id = player.participant.vars.get(f'{topic_prefix}_node_id')
    node_str = str(node_id)
    
    backlog = player.participant.vars.get(f'{topic_prefix}_backlog', {})
    shared_history = player.participant.vars.get(f'{topic_prefix}_shared_history', set())
    
    neighbors = []
    starting_items = []
    
    if baseline_key in Constants.NETWORK_DATA:
        baseline_data = Constants.NETWORK_DATA[baseline_key]
        neighbors = baseline_data.get('network', {}).get(node_str, [])
        starting_items = baseline_data.get('nodes', {}).get(node_str, {}).get('starting_items', [])
    
    new_items = {}
    
    if player.round_number > 1:
        prev_subsession = player.subsession.in_round(player.round_number - 1)
        prev_players = [p for p in prev_subsession.get_players() if p.participant.vars.get('network_treatment') == treatment]
        
        this_player_prev = next((p for p in prev_players if p.participant.vars.get(f'{topic_prefix}_node_id') == node_id), None)
        if this_player_prev:
            shares_data = this_player_prev.field_maybe_none(f'{topic_prefix}_outgoing_shares')
            if shares_data:
                try:
                    for item_id in json.loads(shares_data):
                        shared_history.add(str(item_id).strip().lower())
                except: pass
        player.participant.vars[f'{topic_prefix}_shared_history'] = shared_history

        for n_id in neighbors:
            n_player = next((p for p in prev_players if p.participant.vars.get(f'{topic_prefix}_node_id') == n_id), None)
            if n_player:
                n_shares_data = n_player.field_maybe_none(f'{topic_prefix}_outgoing_shares')
                if n_shares_data:
                    try:
                        for item_id in json.loads(n_shares_data):
                            str_id = str(item_id).strip().lower()
                            if str_id not in shared_history:
                                new_items[str_id] = new_items.get(str_id, 0) + 1
                    except: pass

    backlog = {str(k).strip().lower(): v for k, v in backlog.items() if str(k).strip().lower() not in shared_history}
    feed_item_ids = []

    if player.round_number == 1 and starting_items:
        feed_item_ids = [str(item).strip().lower() for item in starting_items]
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
            pool_old = [k for k in backlog.keys() if k not in feed_item_ids]
            weights_old = [backlog[k] for k in pool_old]
            while len(feed_item_ids) < 4 and pool_old:
                choice = random.choices(pool_old, weights=weights_old, k=1)[0]
                feed_item_ids.append(choice)
                idx = pool_old.index(choice)
                pool_old.pop(idx)
                weights_old.pop(idx)
        
        for k, v in new_items.items():
            clean_key = str(k).strip().lower()
            backlog[clean_key] = backlog.get(clean_key, 0) + v

    feed_items = []
    mapped_ids = []
    
    for item_id in feed_item_ids:
        item_data = next((item for item in news_db if str(item.get('id', '')).strip().lower() == item_id), None)
        if item_data:
            feed_items.append(item_data)
            mapped_ids.append(item_id)
            
    if len(feed_items) < 4:
        needed = 4 - len(feed_items)
        all_ids = [str(item.get('id', '')).strip().lower() for item in news_db if item.get('id')]
        available_pool = [i for i in all_ids if i not in mapped_ids and i not in shared_history and i != '']
        if available_pool:
            padding_ids = random.sample(available_pool, min(needed, len(available_pool)))
            for pad_id in padding_ids:
                pad_data = next((item for item in news_db if str(item.get('id', '')).strip().lower() == pad_id), None)
                if pad_data:
                    feed_items.append(pad_data)
                    mapped_ids.append(pad_id)

    for item_id in mapped_ids:
        if item_id in backlog:
            del backlog[item_id]

    player.participant.vars[f'{topic_prefix}_backlog'] = backlog
    setattr(player, f'{topic_prefix}_current_backlog', json.dumps(backlog))
    setattr(player, f'{topic_prefix}_incoming_feed', json.dumps(feed_items))

def generate_feed_for_player(player: Player):
    if player.participant.vars.get('screened_out', False):
        return
    
    build_topic_feed(player, 'climate', Constants.CLIMATE_NEWS)
    build_topic_feed(player, 'imm', Constants.IMM_NEWS)

class ArrivalGatekeeper(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        if timeout_happened:
            for p in player.in_all_rounds(): p.screened_out = True
            player.participant.vars.update({'screened_out': True, 'is_ghost': True, 'screenout_reason': 'timeout'})
            return

        p_label = str(player.participant.label or f"TEST_USER_{player.id_in_group}")
        player.participant.vars['prolific_id'] = p_label
        
        for p in player.in_all_rounds():
            p.prolific_id = p_label
        
        if p_label not in Constants.MAPPING:
            for p in player.in_all_rounds(): p.screened_out = True
            player.participant.vars.update({'screened_out': True, 'screenout_reason': 'invalid_id'})
            return 

        data = Constants.MAPPING[p_label]
        cat = data.get('category')
        if len(cat) != 2:
            for p in player.in_all_rounds(): p.screened_out = True
            player.participant.vars.update({'screened_out': True, 'screenout_reason': 'invalid_category_format'})
            return

        # Store baseline answers from mapping JSON for the admin report
        player.participant.vars.update({
            'baseline_climate_opinion_1': data.get('climate_opinion_1'),
            'baseline_climate_opinion_2': data.get('climate_opinion_2'),
            'baseline_imm_opinion_1': data.get('imm_opinion_1'),
            'baseline_imm_opinion_2': data.get('imm_opinion_2')
        })

        climate_dir, imm_dir = cat[0], cat[1]
        
        topic_order = random.choice(['climate_first', 'imm_first'])
        player.participant.vars['topic_order'] = topic_order
        for p in player.in_all_rounds(): p.topic_order = topic_order

        with SYSTEM_LOCK:
            assigned_treatment = None
            assigned_climate = None
            assigned_imm = None
            
            mode = player.session.vars.get('network_mode', 'segregated')
            target_treatments = ['segregated', 'integrated'] if mode == 'both' else [mode]
            
            for treatment in target_treatments:
                q_climate = player.session.vars['queues'][treatment][f'climate_{climate_dir}']
                q_imm = player.session.vars['queues'][treatment][f'imm_{imm_dir}']
                
                if len(q_climate) > 0 and len(q_imm) > 0:
                    assigned_treatment = treatment
                    assigned_climate = q_climate.pop(0)
                    assigned_imm = q_imm.pop(0)
                    break

            if assigned_climate is not None and assigned_imm is not None:
                for p in player.in_all_rounds():
                    p.climate_node_id = assigned_climate
                    p.imm_node_id = assigned_imm
                    p.category = cat
                    p.network_treatment = assigned_treatment
                    p.screened_out = False
                player.participant.vars.update({
                    'climate_node_id': assigned_climate,
                    'imm_node_id': assigned_imm,
                    'network_treatment': assigned_treatment,
                    'assigned_category': cat,
                    'screened_out': False
                })
            else:
                for p in player.in_all_rounds(): p.screened_out = True
                player.participant.vars.update({'screened_out': True, 'screenout_reason': 'network_full'})

class CapacityScreenout(Page):
    @staticmethod
    def is_displayed(player: Player):
        is_screened = player.participant.vars.get('screened_out', False)
        is_ghost = player.participant.vars.get('is_ghost', False)
        return player.round_number == 1 and is_screened and not is_ghost

    @staticmethod
    def vars_for_template(player: Player):
        return {'screenout_reason': player.participant.vars.get('screenout_reason', 'unknown')}

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

class FeedTask_First(Page):
    form_model = 'player'
    template_name = 'phase_2/FeedTask.html'
    
    @staticmethod
    def get_form_fields(player: Player):
        prefix = 'climate' if player.topic_order == 'climate_first' else 'imm'
        return [f'{prefix}_outgoing_shares', f'{prefix}_average_feed_size', f'{prefix}_max_feed_size', 
                f'{prefix}_average_pending_items', f'{prefix}_max_pending_items', f'{prefix}_total_time_on_feed']
    
    @staticmethod
    def is_displayed(player: Player):
        return not player.participant.vars.get('screened_out', False)

    @staticmethod
    def vars_for_template(player: Player):
        prefix = 'climate' if player.topic_order == 'climate_first' else 'imm'
        topic_display = "Climate" if prefix == 'climate' else "Immigration"
        vars_dict = {
            'step_indicator': 'Feed 1 of 2',
            'topic_display': topic_display,
            'field_prefix': prefix,
            'deadline_timestamp': calculate_deadline(player.round_number).isoformat()
        }
        vars_dict.update(get_status_vars(player))
        return vars_dict

    @staticmethod
    def js_vars(player: Player):
        prefix = 'climate' if player.topic_order == 'climate_first' else 'imm'
        return {'incoming_feed': json.loads(player.field_maybe_none(f'{prefix}_incoming_feed') or "[]")}

class FeedTask_Second(Page):
    form_model = 'player'
    template_name = 'phase_2/FeedTask.html'
    
    @staticmethod
    def get_form_fields(player: Player):
        prefix = 'imm' if player.topic_order == 'climate_first' else 'climate'
        return [f'{prefix}_outgoing_shares', f'{prefix}_average_feed_size', f'{prefix}_max_feed_size', 
                f'{prefix}_average_pending_items', f'{prefix}_max_pending_items', f'{prefix}_total_time_on_feed']
    
    @staticmethod
    def is_displayed(player: Player):
        return not player.participant.vars.get('screened_out', False)

    @staticmethod
    def vars_for_template(player: Player):
        prefix = 'imm' if player.topic_order == 'climate_first' else 'climate'
        topic_display = "Climate" if prefix == 'climate' else "Immigration"
        vars_dict = {
            'step_indicator': 'Feed 2 of 2',
            'topic_display': topic_display,
            'field_prefix': prefix,
            'deadline_timestamp': calculate_deadline(player.round_number).isoformat()
        }
        vars_dict.update(get_status_vars(player))
        return vars_dict

    @staticmethod
    def js_vars(player: Player):
        prefix = 'imm' if player.topic_order == 'climate_first' else 'climate'
        return {'incoming_feed': json.loads(player.field_maybe_none(f'{prefix}_incoming_feed') or "[]")}

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        if not timeout_happened:
            player.participated_this_round = True

class FinalOpinions(Page):
    form_model = 'player'
    form_fields = ['climate_opinion_1', 'climate_opinion_2', 'imm_opinion_1', 'imm_opinion_2']
    
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == Constants.num_rounds and not player.participant.vars.get('screened_out', False)

    @staticmethod
    def vars_for_template(player: Player):
        return get_status_vars(player)

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
        try: daily_codes = json.loads(codes_json)
        except: daily_codes = {}
        
        vars_dict = {
            'prolific_daily_url': f"https://app.prolific.com/submissions/complete?cc={daily_codes.get(str(player.round_number), 'MISSING')}",
            'next_round_timestamp': calculate_deadline(player.round_number).isoformat()
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
        missed = Constants.num_rounds - completed_rounds
        
        final_base = Constants.FINAL_ROUND_PAY if player.participated_this_round else 0.00
        bonus = Constants.BONUS_AMOUNT if missed <= Constants.MAX_ALLOWED_MISSES else 0.00
        total = final_base + bonus
        
        codes_json = os.environ.get('PROLIFIC_DAILY_CODES', '{}')
        try: daily_codes = json.loads(codes_json)
        except: daily_codes = {}
        
        vars_dict = {
            'completed_rounds': completed_rounds,
            'final_base_pay': f"£{final_base:.2f}",
            'final_bonus_amount': f"£{bonus:.2f}",
            'total_final_payment': f"£{total:.2f}",
            'earned_bonus': bonus > 0,
            'lottery_eligible': (missed == 0),
            'completion_url': f"https://app.prolific.com/submissions/complete?cc={daily_codes.get(str(player.round_number), 'MISSING')}",
            'lottery_ticket': player.participant.code.upper()
        }
        vars_dict.update(get_status_vars(player))
        return vars_dict

page_sequence = [
    ArrivalGatekeeper, 
    CapacityScreenout, 
    FeedTaskGatekeeper, 
    FeedTask_First, 
    FeedTask_Second, 
    FinalOpinions, 
    FinalFeedback, 
    EndOfDayWait, 
    CompletionRedirect
]