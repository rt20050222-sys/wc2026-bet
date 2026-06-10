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

def get_points():
    """管理者設定のポイントを取得（デフォルト: 3連単=15, 3連複=5, チーム=1）"""
    return get_cfg('points', {'trifecta': 15, 'trio': 5, 'team': 1})

def score_prediction(b, r1, r2, r3):
    """
    予想bに対してポイントを計算
    3連単(順番通り)   → trifecta pt
    3連複(3チーム正解・順不同) → trio pt
    1〜2チーム正解   → team pt × 正解チーム数
    ※ 3チーム全正解は3連複扱いのためチーム単位ではカウントしない
    """
    pts = get_points()
    top3 = {r1, r2, r3}
    my = [b.team1, b.team2, b.team3]

    if b.team1 == r1 and b.team2 == r2 and b.team3 == r3:
        return pts['trifecta']              # 3連単
    if set(filter(None, my)) == top3:
        return pts['trio']                  # 3連複（全3チーム正解・順不同）
    hit = sum(1 for t in my if t and t in top3)
    return hit * pts['team']               # 単勝（1〜2チーム正解）

def calc_stats():
    """表示用：予想の集計・重複チェック用"""
    bets = Bet.query.all()
    total_pool = sum(b.amount for b in bets)
    pred_count = {}
    for b in bets:
        key = f"{b.team1}|{b.team2}|{b.team3}"
        pred_count[key] = pred_count.get(key, 0) + 1
    return total_pool, pred_count

def payout_scenarios(participant):
    """
    自分の予想に対して「もし3連単/3連複/N人が当たったら」の推定配当を返す
    """
    if not participant.bets:
        return None
    b = participant.bets[0]
    all_bets = Bet.query.all()
    total_pool = sum(x.amount for x in all_bets)
    if total_pool == 0:
        return None

    # 同じ予想の人数
    same_key = f"{b.team1}|{b.team2}|{b.team3}"
    same_count = sum(1 for x in all_bets if f"{x.team1}|{x.team2}|{x.team3}" == same_key)

    # 現時点の全員ポイント合計（仮に3連単が当たった場合）
    scenarios = {}
    for label, my_pts, others_pts in [
        ('3連単的中（自分だけ）', 15, 0),
        ('3連単的中（同予想全員）', 15, 15 * (same_count - 1)),
        ('3連複的中（自分だけ）', 5, 0),
    ]:
        total_pts = my_pts + others_pts
        if total_pts > 0:
            scenarios[label] = round(my_pts / total_pts * total_pool)

    return scenarios

def final_payouts():
    """
    ポイント按分方式での最終配当
    各自のポイント / 全員のポイント合計 × 総プール
    全員0ポイントの場合は全額返金
    """
    results = get_cfg('results')
    if not results:
        return None
    r1, r2, r3 = results['1st'], results['2nd'], results['3rd']

    all_bets = Bet.query.all()
    total_pool = sum(b.amount for b in all_bets)

    # 各参加者のポイント計算
    pts_map = {}
    for p in Participant.query.all():
        pts = 0
        for b in p.bets:
            pts += score_prediction(b, r1, r2, r3)
        pts_map[p.name] = pts

    total_pts = sum(pts_map.values())

    out = {}
    for name, pts in pts_map.items():
        out[name] = round(pts / total_pts * total_pool) if total_pts > 0 else 0

    # 端数調整（余りなし保証）
    if total_pts > 0:
        diff = total_pool - sum(out.values())
        if diff != 0:
            top = max(pts_map, key=lambda x: pts_map[x])
            out[top] += diff
    else:
        # 全員0ptなら全額返金
        per_person = total_pool // len(out) if out else 0
        out = {name: per_person for name in out}

    return out, pts_map  # pts_mapも返す

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
    fp = final_payouts() if results else None
    payouts = fp[0] if fp else None
    pts_map = fp[1] if fp else None
    return render_template('index.html',
        participant=participant,
        participants=participants,
        buy_in=get_cfg('buy_in', 3000),
        is_open=is_betting_open(),
        deadline=get_cfg('deadline'),
        results=results,
        payouts=payouts,
        pts_map=pts_map,
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

@app.route('/api/change-name', methods=['POST'])
def change_name():
    if 'token' not in session:
        return jsonify({'error': '未登録'}), 401
    new_name = request.json.get('name', '').strip()
    if not new_name or len(new_name) > 20:
        return jsonify({'error': '名前は1〜20文字で入力してください'}), 400
    p = Participant.query.filter_by(token=session['token']).first()
    if not p:
        return jsonify({'error': '参加者が見つかりません'}), 404
    existing = Participant.query.filter_by(name=new_name).first()
    if existing and existing.id != p.id:
        return jsonify({'error': 'その名前はすでに使われています'}), 400
    p.name = new_name
    db.session.commit()
    return jsonify({'ok': True, 'name': new_name})

@app.route('/api/participants-bets')
def participants_bets():
    result = []
    for p in Participant.query.order_by(Participant.joined_at).all():
        pred = None
        if p.bets:
            b = p.bets[0]
            pred = {'team1': b.team1, 'team2': b.team2, 'team3': b.team3}
        result.append({'name': p.name, 'prediction': pred})
    return jsonify(result)

@app.route('/api/my-bet')
def my_bet():
    if 'token' not in session:
        return jsonify({'prediction': None})
    p = Participant.query.filter_by(token=session['token']).first()
    if not p or not p.bets:
        return jsonify({'name': p.name if p else '', 'prediction': None})
    b = p.bets[0]
    return jsonify({
        'name': p.name,
        'prediction': {'team1': b.team1, 'team2': b.team2, 'team3': b.team3}
    })

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
    buy_in = get_cfg('buy_in', 3000)
    t1 = data.get('team1', '').strip()
    t2 = data.get('team2', '').strip()
    t3 = data.get('team3', '').strip()

    if not t1 or not t2 or not t3:
        return jsonify({'error': '1位・2位・3位をすべて選択してください'}), 400
    if len({t1, t2, t3}) < 3:
        return jsonify({'error': '同じチームを複数選択できません'}), 400

    Bet.query.filter_by(participant_id=p.id).delete()
    db.session.add(Bet(
        participant_id=p.id,
        bet_type='prediction',
        team1=t1, team2=t2, team3=t3,
        amount=buy_in,
    ))
    db.session.commit()

    sc = payout_scenarios(p)
    return jsonify({'ok': True, 'scenarios': sc})

@app.route('/api/stats')
def get_stats():
    """集計情報（参加者数・プール・3種別ランキング）"""
    total_pool, _ = calc_stats()
    participant_count = Participant.query.count()
    all_bets = Bet.query.all()
    bet_count = len(all_bets)

    my_scenarios = None
    if 'token' in session:
        p = Participant.query.filter_by(token=session['token']).first()
        if p:
            my_scenarios = payout_scenarios(p)

    # 3連単：完全一致（順番通り）
    trifecta_count = {}
    # 3連複：3チームの組み合わせ（順不同）
    trio_count = {}
    # 単勝：予想に含めたチームの人気（全ポジション横断）
    win_count = {}

    for b in all_bets:
        # 3連単
        tri_key = f"{b.team1} → {b.team2} → {b.team3}"
        trifecta_count[tri_key] = trifecta_count.get(tri_key, 0) + 1
        # 3連複
        trio_key = ' / '.join(sorted(filter(None, [b.team1, b.team2, b.team3])))
        trio_count[trio_key] = trio_count.get(trio_key, 0) + 1
        # 単勝：予想に含めた全チームをカウント（1〜2チーム一致が対象のため全チーム集計）
        for t in filter(None, [b.team1, b.team2, b.team3]):
            win_count[t] = win_count.get(t, 0) + 1

    def to_list(d):
        return sorted(
            [{'key': k, 'count': v,
              'pct': round(v / bet_count * 100) if bet_count else 0}
             for k, v in d.items()],
            key=lambda x: x['count'], reverse=True
        )

    return jsonify({
        'total_pool': total_pool,
        'participant_count': participant_count,
        'bet_count': bet_count,
        'rankings': {
            'trifecta': to_list(trifecta_count),
            'trio':     to_list(trio_count),
            'win':      to_list(win_count),
        },
        'my_scenarios': my_scenarios,
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
            set_cfg('points', {
                'trifecta': int(request.form.get('pt_trifecta', 15)),
                'trio':     int(request.form.get('pt_trio', 5)),
                'team':     int(request.form.get('pt_team', 1)),
            })
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
    total_pool, _ = calc_stats()
    results = get_cfg('results')
    fp = final_payouts() if results else None
    payouts = fp[0] if fp else None
    pts_map = fp[1] if fp else None
    return render_template('admin.html',
        participants=participants,
        buy_in=get_cfg('buy_in', 3000),
        admin_password=get_cfg('admin_password', 'admin1234'),
        football_api_key=get_cfg('football_api_key', ''),
        points=get_points(),
        deadline=get_cfg('deadline', ''),
        is_open=get_cfg('is_open', True),
        total_pool=total_pool,
        results=results,
        payouts=payouts,
        pts_map=pts_map,
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
        set_cfg('buy_in', 3000)
    if not db.session.get(Config, 'is_open'):
        set_cfg('is_open', True)
    if not db.session.get(Config, 'admin_password'):
        set_cfg('admin_password', 'admin1234')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
