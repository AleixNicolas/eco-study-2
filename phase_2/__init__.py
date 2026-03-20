from otree.api import *
import random
import json
import os
import csv
import threading
from datetime import datetime, timedelta, timezone

doc = """
Phase 2: 7-Day Asynchronous Network Experiment with Gamified Rewards.
Includes dynamic pool assignment for 10 High / 10 Low Concern Participants.
Contains Thread-Safe Action Buffer for concurrent user advancement.
"""

# ==========================================
# Module-Level Memory Lock 
# ==========================================
SYSTEM_LOCK = threading.Lock()

class Constants(BaseConstants):
    name_in_url = 'phase_2'
    players_per_group = 20
    num_rounds = 7
    
    PAY_PER_ROUND = 0.50
    BONUS_AMOUNT = 5.00
    MAX_ALLOWED_MISSES = 1
    
    json_path = os.path.join(os.path.dirname(__file__), 'network_map.json')
    if os.path.exists(json_path):
        with open(json_path, encoding='utf-8') as f:
            raw_network = json.load(f)
            NETWORK = {int(k): v for k, v in raw_network.items()}
    else:
        NETWORK = {}

    csv_path = os.path.join(os.path.dirname(__file__), 'news_items.csv')
    if os.path.exists(csv_path):
        with open(csv_path, encoding='utf-8') as f:
            NEWS_ITEMS = list(csv.DictReader(f))
    else:
        NEWS_ITEMS = []

    mapping_data = os.environ.get('PARTICIPANT_MAPPING')
    if mapping_data:
        try:
            MAPPING = json.loads(mapping_data)
        except json.JSONDecodeError:
            print("CRITICAL ERROR: PARTICIPANT_MAPPING environment variable is not valid JSON.")
            MAPPING = {}
    else:
        MAPPING = {}

    QUESTIONS = {
        'opinion_1': {'text': "To what extent do you believe the world's climate is currently changing?", 'left': "Not at all", 'right': "A great deal"},
        'opinion_2': {'text': "How likely do you think it is that climate change will lead to significant natural disasters, such as floods or droughts?", 'left': "Not at all likely", 'right': "Extremely likely"},
        'opinion_3': {'text': "To what extent do you feel a personal responsibility to try to reduce climate change?", 'left': "Not at all", 'right': "A great deal"},
        'opinion_4': {'text': "To what extent do you favor or oppose increasing taxes on fossil fuels (oil, gas, coal) to reduce climate change?", 'left': "Strongly Oppose", 'right': "Strongly Favor"}
    }

# ==========================================
# Python State Manager (Buffer)
# ==========================================
class ActionStateManager:
    @staticmethod
    def register_action(session, user_id, action_data):
        if session.vars.get('is_advancing', False):
            print(f"[Rejected] Action from {user_id} blocked by advancement lock.")
            return False
            
        if 'action_buffer' not in session.vars:
            session.vars['action_buffer'] = []
            
        session.vars['action_buffer'].append({
            'user_id': user_id, 
            'action_data': action_data,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        return True

    @staticmethod
    def filter_valid_actions(buffer):
        processed_users = set()
        valid_actions = []
        
        for entry in buffer:
            u_id = entry['user_id']
            if u_id in processed_users:
                continue
            
            data = entry.get('action_data', {})
            if data.get('invalid'):
                continue
                
            processed_users.add(u_id)
            valid_actions.append(entry)
            
        return valid_actions

    @staticmethod
    def execute_advancement(session):
        with SYSTEM_LOCK:
            if session.vars.get('is_advancing', False):
                return []

            session.vars['is_advancing'] = True
            
            raw_buffer = session.vars.get('action_buffer', [])
            valid_actions = ActionStateManager.filter_valid_actions(raw_buffer)
            
            session.vars['action_buffer'] = []
            session.vars['is_advancing'] = False
            
            return valid_actions

class Subsession(BaseSubsession):
    pass

def creating_session(subsession: Subsession):
    if 'action_buffer' not in subsession.session.vars:
        subsession.session.vars['action_buffer'] = []
    if 'is_advancing' not in subsession.session.vars:
        subsession.session.vars['is_advancing'] = False

def vars_for_admin_report(subsession: Subsession):
    players = subsession.get_players()
    feed_lean_by_cat = {'High_Concern': {}, 'Low_Concern': {}}
    feed_totals = {'High_Concern': 0, 'Low_Concern': 0}
    
    for p in players:
        cat = p.field_maybe_none('category') or "Unknown"
        if cat not in feed_lean_by_cat:
            feed_lean_by_cat[cat] = {}
            feed_totals[cat] = 0
            
        for past_p in p.in_all_rounds():
            feed_str = past_p.field_maybe_none('incoming_feed')
            if feed_str and feed_str != "[]":
                try:
                    feed_items = json.loads(feed_str)
                    for item in feed_items:
                        lean = item.get('leaning', 'Unknown')
                        feed_lean_by_cat[cat][lean] = feed_lean_by_cat[cat].get(lean, 0) + 1
                        feed_totals[cat] += 1
                except json.JSONDecodeError:
                    pass

    feed_lean_percentages = {}
    for cat, leanings in feed_lean_by_cat.items():
        feed_lean_percentages[cat] = {}
        total = feed_totals[cat]
        if total > 0:
            for lean, count in leanings.items():
                feed_lean_percentages[cat][lean] = round((count / total) * 100, 1)

    opinion_change_lists = {'High_Concern': {1: [], 2: [], 3: [], 4: []}, 
                            'Low_Concern': {1: [], 2: [], 3: [], 4: []}}
                            
    for p in players:
        cat = p.field_maybe_none('category') or "Unknown"
        if cat not in opinion_change_lists:
            opinion_change_lists[cat] = {1: [], 2: [], 3: [], 4: []}
            
        for past_p in p.in_all_rounds():
            if past_p.field_maybe_none('opinion_1') is not None:
                for i in range(1, 5):
                    final_val = past_p.field_maybe_none(f'opinion_{i}')
                    baseline_val = p.participant.vars.get(f'baseline_opinion_{i}')
                    
                    if final_val is not None and baseline_val is not None:
                        change = final_val - baseline_val
                        opinion_change_lists[cat][i].append(change)
                break 

    avg_opinion_change = {}
    for cat, ops in opinion_change_lists.items():
        avg_opinion_change[cat] = {}
        for i in range(1, 5):
            vals = ops[i]
            if vals:
                avg = sum(vals) / len(vals)
                avg_str = f"+{avg:.2f}" if avg > 0 else f"{avg:.2f}"
                avg_opinion_change[cat][f'opinion_{i}'] = avg_str
            else:
                avg_opinion_change[cat][f'opinion_{i}'] = "No Data"

    return {
        'feed_lean_percentages': feed_lean_percentages,
        'avg_opinion_change': avg_opinion_change,
        'total_players': len(players)
    }

class Group(BaseGroup):
    pass

class Player(BasePlayer):
    node_id = models.IntegerField(blank=True, null=True)
    category = models.StringField(blank=True) 
    screened_out = models.BooleanField(initial=False)
    
    incoming_feed = models.LongStringField(initial="[]", blank=True)
    outgoing_shares = models.LongStringField(initial="[]", blank=True)
    average_feed_size = models.FloatField(blank=True)
    max_feed_size = models.IntegerField(blank=True)
    average_pending_items = models.FloatField(blank=True)
    max_pending_items = models.IntegerField(blank=True)
    total_time_on_feed = models.FloatField(blank=True)
    
    participated_this_round = models.BooleanField(initial=False)
    
    opinion_1 = models.IntegerField(choices=[1, 2, 3, 4, 5, 6, 7], widget=widgets.RadioSelectHorizontal)
    opinion_2 = models.IntegerField(choices=[1, 2, 3, 4, 5, 6, 7], widget=widgets.RadioSelectHorizontal)
    opinion_3 = models.IntegerField(choices=[1, 2, 3, 4, 5, 6, 7], widget=widgets.RadioSelectHorizontal)
    opinion_4 = models.IntegerField(choices=[1, 2, 3, 4, 5, 6, 7], widget=widgets.RadioSelectHorizontal)
    
    satisfaction = models.IntegerField(choices=[1, 2, 3, 4, 5], label="Overall, how satisfied were you with your experience?", widget=widgets.RadioSelectHorizontal)
    clarity = models.IntegerField(choices=[1, 2, 3, 4, 5], label="How clear were the daily instructions?", widget=widgets.RadioSelectHorizontal)
    echo_chamber = models.IntegerField(choices=[1, 2, 3, 4, 5, 6, 7], label="To what extent did you feel you were in an 'echo chamber'?", widget=widgets.RadioSelectHorizontal)
    neighbor_similarity = models.IntegerField(choices=[1, 2, 3, 4, 5, 6, 7], label="How similar do you think your network neighbors' opinions were to your own?", widget=widgets.RadioSelectHorizontal)
    final_comments = models.LongStringField(label="Comments or questions regarding the experiment.", blank=True)


# ==========================================
# Reusable Header Vars Helper
# ==========================================
def get_status_vars(player: Player):
    # Earnings update immediately based on ALL rounds (including the one just finished)
    all_rounds = player.in_all_rounds()
    completed_total = sum([1 for p in all_rounds if p.field_maybe_none('participated_this_round') == True])
    current_earnings = completed_total * Constants.PAY_PER_ROUND
    
    # Shield/Chest calculate based on PREVIOUS rounds, locking in status at the start of the day
    past_rounds = player.in_previous_rounds()
    completed_past = sum([1 for p in past_rounds if p.field_maybe_none('participated_this_round') == True])
    missed_rounds_start = (player.round_number - 1) - completed_past
    
    shield_active = missed_rounds_start <= 0
    chest_active = missed_rounds_start <= Constants.MAX_ALLOWED_MISSES
    
    return {
        'current_round': player.round_number,
        'total_rounds': Constants.num_rounds,
        'current_earnings': f"${current_earnings:.2f}",
        'shield_active': shield_active,
        'chest_active': chest_active,
        'bonus_amount': f"${Constants.BONUS_AMOUNT:.2f}"
    }

# ==========================================
# Pages
# ==========================================
class ArrivalGatekeeper(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        if timeout_happened:
            player.screened_out = True
            player.participant.vars['screened_out'] = True
            player.participant.vars['is_ghost'] = True
            return

        p_label = player.participant.label or f"TEST_USER_{player.id_in_group}"
        player.participant.vars['prolific_id'] = p_label
        
        if p_label in Constants.MAPPING:
            data = Constants.MAPPING[p_label]
            cat = data.get('category')
            player.participant.vars['assigned_category'] = cat
            player.participant.vars['baseline_opinion_1'] = data.get('opinion_1')
            player.participant.vars['baseline_opinion_2'] = data.get('opinion_2')
            player.participant.vars['baseline_opinion_3'] = data.get('opinion_3')
            player.participant.vars['baseline_opinion_4'] = data.get('opinion_4')
        else:
            cat = 'High_Concern' if player.id_in_group <= 10 else 'Low_Concern'
            player.participant.vars['assigned_category'] = cat

        player.category = cat

        with SYSTEM_LOCK:
            all_players = player.subsession.get_players()
            assigned_nodes = [
                p.field_maybe_none('node_id') 
                for p in all_players 
                if p.field_maybe_none('node_id') is not None
            ]
            
            target_nodes = list(range(1, 11)) if cat == 'High_Concern' else list(range(11, 21))
            available_nodes = [n for n in target_nodes if n not in assigned_nodes]

            if available_nodes:
                assigned_node = min(available_nodes)
                player.node_id = assigned_node
                player.participant.vars['node_id'] = assigned_node
                player.screened_out = False
                player.participant.vars['screened_out'] = False 
            else:
                player.screened_out = True
                player.participant.vars['screened_out'] = True 

class CapacityScreenout(Page):
    @staticmethod
    def is_displayed(player: Player):
        is_screened = player.participant.vars.get('screened_out', False)
        is_ghost = player.participant.vars.get('is_ghost', False)
        return player.round_number == 1 and is_screened and not is_ghost

    @staticmethod
    def get_timeout_seconds(player: Player):
        return 10  

class NetworkWait(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1 and not player.participant.vars.get('screened_out', False)

    @staticmethod
    def vars_for_template(player: Player):
        all_players = player.subsession.get_players()
        assigned_count = len([p for p in all_players if p.field_maybe_none('node_id') is not None])
        
        vars_dict = {
            'network_full': assigned_count >= 20,
            'start_date': player.session.config.get('start_date', 'the specified date')
        }
        vars_dict.update(get_status_vars(player))
        return vars_dict

    @staticmethod
    def get_timeout_seconds(player: Player):
        all_players = player.subsession.get_players()
        assigned_count = len([p for p in all_players if p.field_maybe_none('node_id') is not None])
        return 1 if assigned_count >= 20 else 86400 * 30

class FeedTaskGatekeeper(Page):
    @staticmethod
    def is_displayed(player: Player):
        return not player.participant.vars.get('screened_out', False)

    @staticmethod
    def vars_for_template(player: Player):
        try:
            player.node_id = player.participant.vars.get('node_id')
            player.category = player.participant.vars.get('assigned_category')

            if 'backlog' not in player.participant.vars:
                player.participant.vars['backlog'] = {}

            current_round = player.round_number
            backlog = player.participant.vars['backlog']
            
            if current_round == 1:
                all_players_r1 = player.subsession.get_players()
                neighbors = Constants.NETWORK.get(player.node_id, [])
                
                for n_id in neighbors:
                    n_player = next((p for p in all_players_r1 if p.field_maybe_none('node_id') == n_id), None)
                    if n_player and n_player.participant.label:
                        n_label = n_player.participant.label
                        n_data = Constants.MAPPING.get(n_label, {})
                        n_shares = n_data.get('outgoing_shares', [])
                        for item_id in n_shares:
                            item_id = str(item_id)
                            backlog[item_id] = backlog.get(item_id, 0) + 1

            if current_round > 1:
                prev_subsession = player.subsession.in_round(current_round - 1)
                neighbors = Constants.NETWORK.get(player.node_id, [])
                
                prev_players = prev_subsession.get_players()
                for n_id in neighbors:
                    n_player = next((p for p in prev_players if p.field_maybe_none('node_id') == n_id), None)
                    if n_player and n_player.field_maybe_none('outgoing_shares'):
                        try:
                            n_shares = json.loads(n_player.outgoing_shares)
                            if isinstance(n_shares, list):
                                for item_id in n_shares:
                                    item_id = str(item_id) 
                                    backlog[item_id] = backlog.get(item_id, 0) + 1
                        except Exception:
                            pass

            feed_item_ids = []

            if len(backlog) > 4:
                pool = list(backlog.keys())
                weights = [backlog[k] for k in pool]
                while len(feed_item_ids) < 4 and pool:
                    choice = random.choices(pool, weights=weights, k=1)[0]
                    feed_item_ids.append(choice)
                    idx = pool.index(choice)
                    pool.pop(idx)
                    weights.pop(idx)
            else:
                feed_item_ids = list(backlog.keys())

            if len(feed_item_ids) < 4:
                needed = 4 - len(feed_item_ids)
                all_ids = [str(item.get('id', '')) for item in Constants.NEWS_ITEMS]
                available_pool = [i for i in all_ids if i not in feed_item_ids and i != '']
                
                if needed <= len(available_pool):
                    padding_items = random.sample(available_pool, needed)
                else:
                    padding_items = available_pool
                
                feed_item_ids.extend(padding_items)

            for item_id in feed_item_ids:
                if item_id in backlog:
                    del backlog[item_id]

            feed_items = []
            for item_id in feed_item_ids:
                item_data = next((item for item in Constants.NEWS_ITEMS if str(item.get('id', '')) == str(item_id)), None)
                if item_data:
                    feed_items.append(item_data)
                    
            player.incoming_feed = json.dumps(feed_items)
            return get_status_vars(player)
            
        except Exception as e:
            print(f"CRITICAL ERROR AVOIDED in Round {player.round_number}: {e}")
            player.incoming_feed = "[]"
            return get_status_vars(player)

class FeedTask(Page):
    form_model = 'player'
    form_fields = [
        'outgoing_shares', 'average_feed_size', 'max_feed_size', 
        'average_pending_items', 'max_pending_items', 'total_time_on_feed'
    ]
    
    @staticmethod
    def is_displayed(player: Player):
        return not player.participant.vars.get('screened_out', False)

    @staticmethod
    def vars_for_template(player: Player):
        return get_status_vars(player)

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
    form_fields = ['satisfaction', 'clarity', 'echo_chamber', 'neighbor_similarity', 'final_comments']
    
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
    def get_timeout_seconds(player: Player):
        now = datetime.now(timezone.utc)
        release_hour = player.session.config.get('daily_start_hour_utc', 14)
        target = now.replace(hour=release_hour, minute=0, second=0, microsecond=0)
        
        if target <= now:
            target += timedelta(days=1)
            
        return (target - now).total_seconds()

    @staticmethod
    def vars_for_template(player: Player):
        now = datetime.now(timezone.utc)
        release_hour = player.session.config.get('daily_start_hour_utc', 14)
        target = now.replace(hour=release_hour, minute=0, second=0, microsecond=0)
        
        if target <= now:
            target += timedelta(days=1)
            
        vars_dict = {
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
        
        base_pay = completed_rounds * Constants.PAY_PER_ROUND
        bonus = Constants.BONUS_AMOUNT if missed_rounds <= Constants.MAX_ALLOWED_MISSES else 0.00
        total_pay = base_pay + bonus
        
        lottery_eligible = (missed_rounds == 0)
        completion_url = player.session.config.get('completion_url', '')
        
        vars_dict = {
            'completed_rounds': completed_rounds,
            'base_pay': f"${base_pay:.2f}",
            'bonus_amount': f"${bonus:.2f}",
            'total_pay': f"${total_pay:.2f}",
            'earned_bonus': bonus > 0,
            'lottery_eligible': lottery_eligible,
            'completion_url': completion_url
        }
        vars_dict.update(get_status_vars(player))
        return vars_dict

page_sequence = [
    ArrivalGatekeeper, 
    CapacityScreenout, 
    NetworkWait,
    FeedTaskGatekeeper, 
    FeedTask, 
    FinalOpinions, 
    FinalFeedback, 
    EndOfDayWait, 
    CompletionRedirect
]