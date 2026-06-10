import os
import json
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from flask import (Flask, render_template, request, jsonify,
                   session, redirect, url_for)
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'wc2026-please-change-in-prod')

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////home/rt20050222sys/wc2026_bet/bets.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ── チーム一覧（2026 W杯 48カ国・正式） ────────────────────────
TEAMS = [
    # CONMEBOL（南米 6）
    "アルゼンチン", "ブラジル", "ウルグアイ", "コロンビア", "エクアドル", "パラグアイ",
    # UEFA（欧州 16）
    "フランス", "スペイン", "イングランド", "ドイツ", "ポルトガル",
    "オランダ", "ベルギー", "クロアチア", "スイス", "オーストリア",
    "チェコ", "スコットランド", "トルコ", "ノルウェー", "スウェーデン",
    "ボスニア・ヘルツェゴビナ",
    # CONCACAF（北中米カリブ 6）
    "アメリカ", "メキシコ", "カナダ", "パナマ", "ハイチ", "キュラソー",
    # AFC（アジア 9）
    "日本", "韓国", "オーストラリア", "イラン", "サウジアラビア",
    "ウズベキスタン", "イラク", "ヨルダン", "カタール",
    # CAF（アフリカ 10）
    "モロッコ", "セネガル", "コートジボワール", "エジプト",
    "コンゴ民主共和国", "南アフリカ", "ガーナ", "アルジェリア",
    "チュニジア", "カーボベルデ",
    # OFC（オセアニア 1）
    "ニュージーランド",
]

# football-data.org の英語名 → 日本語名マッピング
TEAM_NAME_MAP = {
    "Argentina": "アルゼンチン", "Brazil": "ブラジル", "Uruguay": "ウルグアイ",
    "Colombia": "コロンビア", "Ecuador": "エクアドル", "Paraguay": "パラグアイ",
    "France": "フランス", "Spain": "スペイン", "England": "イングランド",
    "Germany": "ドイツ", "Portugal": "ポルトガル", "Netherlands": "オランダ",
    "Belgium": "ベルギー", "Croatia": "クロアチア", "Switzerland": "スイス",
    "Austria": "オーストリア", "Czech Republic": "チェコ", "Czechia": "チェコ",
    "Scotland": "スコットランド", "Turkey": "トルコ", "Norway": "ノルウェー",
    "Sweden": "スウェーデン", "Bosnia and Herzegovina": "ボスニア・ヘルツェゴビナ",
    "United States": "アメリカ", "Mexico": "メキシコ", "Canada": "カナダ",
    "Panama": "パナマ", "Haiti": "ハイチ", "Curaçao": "キュラソー", "Curacao": "キュラソー",
    "Japan": "日本", "Korea Republic": "韓国", "South Korea": "韓国",
    "Australia": "オーストラリア", "Iran": "イラン", "Saudi Arabia": "サウジアラビア",
    "Uzbekistan": "ウズベキスタン", "Iraq": "イラク", "Jordan": "ヨルダン",
    "Qatar": "カタール",
    "Morocco": "モロッコ", "Senegal": "セネガル", "Côte d'Ivoire": "コートジボワール",
    "Ivory Coast": "コートジボワール", "Egypt": "エジプト",
    "DR Congo": "コンゴ民主共和国", "Democratic Republic of Congo": "コンゴ民主共和国",
    "South Africa": "南アフリカ", "Ghana": "ガーナ", "Algeria": "アルジェリア",
    "Tunisia": "チュニジア", "Cape Verde": "カーボベルデ",
    "New Zealand": "ニュージーランド",
}

def team_ja(name):
    return TEAM_NAME_MAP.get(name, name)

# ── 試合データキャッシュ ──────────────────────────────────────────
_match_cache = {'data': None, 'updated': None}
_standings_cache = {'data': None, 'updated': None}
CACHE_MINUTES = 5

def fetch_football_api(path):
    api_key = get_cfg('football_api_key', '')
    if not api_key:
        return None
    url = f'https://api.football-data.org/v4/{path}'
    req = urllib.request.Request(url, headers={'X-Auth-Token': api_key})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode())
    except Exception:
        return None

def get_matches():
    now = datetime.now(timezone.utc)
    if (_match_cache['data'] is not None and _match_cache['updated'] and
            now - _match_cache['updated'] < timedelta(minutes=CACHE_MINUTES)):
        return _match_cache['data']
    data = fetch_football_api('competitions/WC/matches')
    if data:
        _match_cache['data'] = data
        _match_cache['updated'] = now
    return _match_cache['data']

def get_standings():
    now = datetime.now(timezone.utc)
    if (_standings_cache['data'] is not None and _standings_cache['updated'] and
            now - _standings_cache['updated'] < timedelta(minutes=CACHE_MINUTES)):
        return _standings_cache['data']
    data = fetch_football_api('competitions/WC/standings')
    if data:
        _standings_cache['data'] = data
        _standings_cache['updated'] = now
    return _standings_cache['data']

STAGE_LABELS = {
    'GROUP_STAGE': 'グループステージ',
    'LAST_32': 'ラウンド32',
    'LAST_16': 'ラウンド16',
    'QUARTER_FINALS': '準々決勝',
    'SEMI_FINALS': '準決勝',
    'THIRD_PLACE': '3位決定戦',
    'FINAL': '決勝',
}

STATUS_LABELS = {
    'SCHEDULED': '未定', 'TIMED': '開始前',
    'IN_PLAY': '🔴 試合中', 'PAUSED': '🟡 ハーフタイム',
    'FINISHED': '終了', 'POSTPONED': '延期', 'CANCELLED': '中止',
}

# ── モデル ────────────────────────────────────────────────────────
class Config(db.Model):
    key   = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.Text)

class Participant(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(50), unique=True, nullable=False)
    token     = db.Column(db.String(36), unique=True,
                          default=lambda: str(uuid.uuid4()))
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    bets      = db.relationship('Bet', backref='participant', lazy=True,
                                cascade='all, delete-orphan')

class Bet(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participant.id'),
                               nullable=False)
    bet_type       = db.Column(db.String(20), nullable=False)
    team1          = db.Column(db.String(50))
    team2          = db.Column(db.String(50))
    team3          = db.Column(db.String(50))
    amount         = db.Column(db.Integer, nullable=False)
    updated_at     = db.Column(db.DateTime,
                               default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))

# ── ヘルパー ──────────────────────────────────────────────────────
def get_cfg(key, default=None):
    c = db.session.get(Config, key)
    return json.loads(c.value) if c else default

def set_cfg(key, value):
    c = db.session.get(Config, key) or Config(key=key)
    c.value = json.dumps(value, ensure_ascii=False)
    db.session.add(c)
    db.session.commit()

def is_betting_open():
    if not get_cfg('is_open', True):
        return False
    deadline = get_cfg('deadline')
    if deadline:
        return datetime.now(timezone.utc) < datetime.fromisoformat(deadline)
    return True

def calc_pools():
    """各賭け種別のプール・賭け分布を集計"""
    bets = Bet.query.all()
    pools  = {'trifecta': {}, 'trio': {}, 'win': {}}
    totals = {'trifecta': 0, 'trio': 0, 'win': 0}

    for b in bets:
        bt = b.bet_type
        totals[bt] += b.amount
        if bt == 'trifecta':
            key = f"{b.team1}|{b.team2}|{b.team3}"
        elif bt == 'trio':
            key = '|'.join(sorted(filter(None, [b.team1, b.team2, b.team3])))
        else:
            key = b.team1 or ''
        pools[bt][key] = pools[bt].get(key, 0) + b.amount

    return pools, totals

def odds_for(pools, totals):
    """パリミュチュエルオッズ計算"""
    result = {}
    for bt, pool in pools.items():
        result[bt] = {}
        for key, amt in pool.items():
            result[bt][key] = round(totals[bt] / amt, 2) if amt else 0
    return result

def expected_payout(participant):
    pools, totals = calc_pools()
    odd = odds_for(pools, totals)
    total = 0
    for b in participant.bets:
        bt = b.bet_type
        if bt == 'trifecta':
            key = f"{b.team1}|{b.team2}|{b.team3}"
        elif bt == 'trio':
            key = '|'.join(sorted(filter(None, [b.team1, b.team2, b.team3])))
        else:
            key = b.team1 or ''
        if key in odd.get(bt, {}):
            total += b.amount * odd[bt][key]
    return round(total)

def final_payouts():
    results = get_cfg('results')
    if not results:
        return None
    r1, r2, r3 = results['1st'], results['2nd'], results['3rd']
    trio_key = '|'.join(sorted([r1, r2, r3]))
    pools, totals = calc_pools()

    out = {}
    for p in Participant.query.all():
        pay = 0
        for b in p.bets:
            bt = b.bet_type
            if bt == 'trifecta':
                if b.team1 == r1 and b.team2 == r2 and b.team3 == r3:
                    w_total = pools['trifecta'].get(f"{r1}|{r2}|{r3}", 0)
                    if w_total:
                        pay += b.amount * totals['trifecta'] / w_total
            elif bt == 'trio':
                my_key = '|'.join(sorted(filter(None, [b.team1, b.team2, b.team3])))
                if my_key == trio_key:
                    w_total = pools['trio'].get(trio_key, 0)
                    if w_total:
                        pay += b.amount * totals['trio'] / w_total
            elif bt == 'win':
                if b.team1 == r1:
                    w_total = pools['win'].get(r1, 0)
                    if w_total:
                        pay += b.amount * totals['win'] / w_total
        out[p.name] = round(pay)
    return out

# ── 試合・順位ルート ──────────────────────────────────────────────
@app.route('/matches')
def matches_page():
    participant = None
    if 'token' in session:
        participant = Participant.query.filter_by(token=session['token']).first()
    return render_template('matches.html', participant=participant)

@app.route('/api/matches')
def api_matches():
    data = get_matches()
    if not data:
        api_key = get_cfg('football_api_key', '')
        if not api_key:
            return jsonify({'error': 'API_KEY_NOT_SET'})
        return jsonify({'error': 'FETCH_FAILED'})

    now = datetime.now(timezone.utc)
    matches = []
    for m in data.get('matches', []):
        utc_str = m.get('utcDate', '')
        try:
            kick_off = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
            jst = kick_off + timedelta(hours=9)
            kick_off_jst = jst.strftime('%m/%d %H:%M')
        except Exception:
            kick_off_jst = utc_str
            kick_off = None

        status = m.get('status', '')
        score = m.get('score', {})
        ft = score.get('fullTime', {})
        ht = score.get('halfTime', {})

        home = team_ja(m.get('homeTeam', {}).get('name', ''))
        away = team_ja(m.get('awayTeam', {}).get('name', ''))

        matches.append({
            'id': m.get('id'),
            'stage': STAGE_LABELS.get(m.get('stage', ''), m.get('stage', '')),
            'group': m.get('group', ''),
            'kick_off_jst': kick_off_jst,
            'status': STATUS_LABELS.get(status, status),
            'status_raw': status,
            'home': home,
            'away': away,
            'home_score': ft.get('home'),
            'away_score': ft.get('away'),
            'home_ht': ht.get('home'),
            'away_ht': ht.get('away'),
        })

    updated = _match_cache['updated']
    updated_jst = (updated + timedelta(hours=9)).strftime('%H:%M:%S') if updated else '--'
    return jsonify({'matches': matches, 'updated_jst': updated_jst})

@app.route('/api/standings')
def api_standings():
    data = get_standings()
    if not data:
        return jsonify({'error': 'NO_DATA'})

    groups = []
    for s in data.get('standings', []):
        if s.get('type') != 'TOTAL':
            continue
        group_name = s.get('group', '').replace('GROUP_', 'グループ ')
        table = []
        for row in s.get('table', []):
            table.append({
                'pos': row.get('position'),
                'team': team_ja(row.get('team', {}).get('name', '')),
                'played': row.get('playedGames', 0),
                'won': row.get('won', 0),
                'draw': row.get('draw', 0),
                'lost': row.get('lost', 0),
                'gf': row.get('goalsFor', 0),
                'ga': row.get('goalsAgainst', 0),
                'gd': row.get('goalDifference', 0),
                'pts': row.get('points', 0),
            })
        groups.append({'group': group_name, 'table': table})

    updated = _standings_cache['updated']
    updated_jst = (updated + timedelta(hours=9)).strftime('%H:%M:%S') if updated else '--'
    return jsonify({'groups': groups, 'updated_jst': updated_jst})

# ── ルート ────────────────────────────────────────────────────────
@app.route('/')
def index():
    participant = None
    if 'token' in session:
        participant = Participant.query.filter_by(token=session['token']).first()
    participants = Participant.query.order_by(Participant.joined_at).all()
    results = get_cfg('results')
    payouts = final_payouts() if results else None
    return render_template('index.html',
        participant=participant,
        participants=participants,
        buy_in=get_cfg('buy_in', 1000),
        is_open=is_betting_open(),
        deadline=get_cfg('deadline'),
        results=results,
        payouts=payouts,
        teams=TEAMS,
    )

@app.route('/register', methods=['POST'])
def register():
    name = request.form.get('name', '').strip()
    if not name:
        return redirect(url_for('index'))
    p = Participant.query.filter_by(name=name).first()
    if not p:
        p = Participant(name=name)
        db.session.add(p)
        db.session.commit()
    session['token'] = p.token
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/api/bet', methods=['POST'])
def place_bet():
    if 'token' not in session:
        return jsonify({'error': '未登録'}), 401
    if not is_betting_open():
        return jsonify({'error': '締め切り済み'}), 403

    p = Participant.query.filter_by(token=session['token']).first()
    if not p:
        return jsonify({'error': '参加者が見つかりません'}), 404

    data = request.json
    buy_in = get_cfg('buy_in', 1000)
    bets_data = data.get('bets', [])

    # バリデーション：合計金額チェック
    total = sum(int(b.get('amount', 0)) for b in bets_data)
    if total != buy_in:
        return jsonify({'error': f'掛け金の合計を {buy_in}円 にしてください（現在: {total}円）'}), 400

    # チーム重複チェック（3連単・3連複）
    for b in bets_data:
        teams = [b.get('team1'), b.get('team2'), b.get('team3')]
        teams = [t for t in teams if t]
        if len(teams) != len(set(teams)):
            return jsonify({'error': '同じチームを複数選択できません'}), 400

    # 既存の賭けを削除して置き換え
    Bet.query.filter_by(participant_id=p.id).delete()
    for b in bets_data:
        db.session.add(Bet(
            participant_id=p.id,
            bet_type=b['type'],
            team1=b.get('team1'),
            team2=b.get('team2'),
            team3=b.get('team3'),
            amount=int(b['amount']),
        ))
    db.session.commit()
    return jsonify({'ok': True, 'expected_payout': expected_payout(p)})

@app.route('/api/odds')
def get_odds():
    pools, totals = calc_pools()
    odd = odds_for(pools, totals)
    participant_count = Participant.query.count()
    bet_count = Participant.query.join(Bet).distinct().count()

    my_expected = None
    if 'token' in session:
        p = Participant.query.filter_by(token=session['token']).first()
        if p:
            my_expected = expected_payout(p)

    # 各賭け種別の上位予想を集計
    top = {}
    for bt, pool in pools.items():
        sorted_pool = sorted(pool.items(), key=lambda x: x[1], reverse=True)[:5]
        top[bt] = [{'key': k, 'amount': v, 'odds': odd[bt].get(k, 0),
                    'pct': round(v / totals[bt] * 100) if totals[bt] else 0}
                   for k, v in sorted_pool]

    return jsonify({
        'totals': totals,
        'total_pool': sum(totals.values()),
        'participant_count': participant_count,
        'bet_count': bet_count,
        'top': top,
        'my_expected': my_expected,
    })

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        action = request.form.get('action')
        admin_pw = get_cfg('admin_password', 'admin1234')

        if action == 'login':
            if request.form.get('password') == admin_pw:
                session['is_admin'] = True
            return redirect(url_for('admin'))

        if not session.get('is_admin'):
            return redirect(url_for('admin'))

        if action == 'config':
            set_cfg('buy_in', int(request.form['buy_in']))
            set_cfg('admin_password', request.form['admin_password'])
            set_cfg('football_api_key', request.form.get('football_api_key', '').strip())
            deadline_str = request.form.get('deadline', '').strip()
            if deadline_str:
                dt = datetime.fromisoformat(deadline_str).replace(tzinfo=timezone.utc)
                set_cfg('deadline', dt.isoformat())
            else:
                set_cfg('deadline', None)
            set_cfg('is_open', request.form.get('is_open') == 'on')
            _match_cache['data'] = None
            _standings_cache['data'] = None

        elif action == 'results':
            set_cfg('results', {
                '1st': request.form['first'],
                '2nd': request.form['second'],
                '3rd': request.form['third'],
            })

        elif action == 'delete_participant':
            pid = int(request.form['pid'])
            p = db.session.get(Participant, pid)
            if p:
                db.session.delete(p)
                db.session.commit()

        elif action == 'reset_results':
            set_cfg('results', None)

        return redirect(url_for('admin'))

    if not session.get('is_admin'):
        return render_template('admin_login.html')

    participants = Participant.query.order_by(Participant.joined_at).all()
    pools, totals = calc_pools()
    results = get_cfg('results')
    payouts = final_payouts() if results else None
    return render_template('admin.html',
        participants=participants,
        buy_in=get_cfg('buy_in', 1000),
        admin_password=get_cfg('admin_password', 'admin1234'),
        football_api_key=get_cfg('football_api_key', ''),
        deadline=get_cfg('deadline', ''),
        is_open=get_cfg('is_open', True),
        totals=totals,
        results=results,
        payouts=payouts,
        teams=TEAMS,
    )

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))

# ── 初期化 ────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    if not db.session.get(Config, 'buy_in'):
        set_cfg('buy_in', 1000)
    if not db.session.get(Config, 'is_open'):
        set_cfg('is_open', True)
    if not db.session.get(Config, 'admin_password'):
        set_cfg('admin_password', 'admin1234')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
