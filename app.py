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

# ── チーム一覧＆オッズ（添付資料に基づく48チーム） ──────────────
# オッズ順に並べておく（予想フォームの表示順）
TEAMS_WITH_ODDS = [
    ("スペイン",         5.5),
    ("フランス",         5.8),
    ("イングランド",     8.0),
    ("ポルトガル",       9.5),
    ("アルゼンチン",    10.0),
    ("ブラジル",        10.0),
    ("ドイツ",          15.0),
    ("オランダ",        23.0),
    ("ベルギー",        29.0),
    ("ノルウェー",      34.0),
    ("コロンビア",      41.0),
    ("モロッコ",        51.0),
    ("クロアチア",      67.0),
    ("アメリカ",        81.0),
    ("日本",           101.0),
    ("ウルグアイ",     101.0),
    ("メキシコ",       126.0),
    ("デンマーク",     126.0),
    ("スイス",         151.0),
    ("セネガル",       151.0),
    ("オーストリア",   176.0),
    ("エジプト",       201.0),
    ("スウェーデン",   201.0),
    ("セルビア",       251.0),
    ("カナダ",         251.0),
    ("ポーランド",     301.0),
    ("韓国",           351.0),
    ("オーストラリア", 501.0),
    ("チュニジア",     501.0),
    ("パラグアイ",     501.0),
    ("コートジボワール", 501.0),
    ("エクアドル",     501.0),
    ("アルジェリア",   501.0),
    ("ナイジェリア",   751.0),
    ("カメルーン",     751.0),
    ("ペルー",         751.0),
    ("チリ",          1001.0),
    ("コスタリカ",    1001.0),
    ("ウェールズ",    1001.0),
    ("ギリシャ",      1001.0),
    ("スコットランド",1001.0),
    ("イラン",        1001.0),
    ("サウジアラビア",1501.0),
    ("南アフリカ",    1501.0),
    ("ニュージーランド",2001.0),
    ("パナマ",        2001.0),
    ("ホンジュラス",  2501.0),
    ("キュラソー",    3001.0),
]

TEAMS         = [t for t, _ in TEAMS_WITH_ODDS]
ODDS_MAP_DEFAULT = {t: o for t, o in TEAMS_WITH_ODDS}

def get_odds_config():
    """DB保存のオッズを取得（未設定ならデフォルト値）"""
    stored = get_cfg('team_odds', None)
    if stored and isinstance(stored, dict):
        return stored
    return ODDS_MAP_DEFAULT.copy()

def get_team_odds(name):
    return get_odds_config().get(name, 1.0)

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
_match_cache    = {'data': None, 'updated': None}
_standings_cache = {'data': None, 'updated': None}
_odds_cache      = {'data': None, 'updated': None}
CACHE_MINUTES = 5

# ── 歴代W杯結果 ───────────────────────────────────────────────────
WC_HISTORY = [
    (1930,"ウルグアイ","アルゼンチン","アメリカ"),
    (1934,"イタリア","チェコスロバキア","ドイツ"),
    (1938,"イタリア","ハンガリー","ブラジル"),
    (1950,"ウルグアイ","ブラジル","スウェーデン"),
    (1954,"西ドイツ","ハンガリー","オーストリア"),
    (1958,"ブラジル","スウェーデン","フランス"),
    (1962,"ブラジル","チェコスロバキア","チリ"),
    (1966,"イングランド","西ドイツ","ポルトガル"),
    (1970,"ブラジル","イタリア","西ドイツ"),
    (1974,"西ドイツ","オランダ","ポーランド"),
    (1978,"アルゼンチン","オランダ","ブラジル"),
    (1982,"イタリア","西ドイツ","ポーランド"),
    (1986,"アルゼンチン","西ドイツ","フランス"),
    (1990,"西ドイツ","アルゼンチン","イタリア"),
    (1994,"ブラジル","イタリア","スウェーデン"),
    (1998,"フランス","ブラジル","クロアチア"),
    (2002,"ブラジル","ドイツ","トルコ"),
    (2006,"イタリア","フランス","ドイツ"),
    (2010,"スペイン","オランダ","ドイツ"),
    (2014,"ドイツ","アルゼンチン","オランダ"),
    (2018,"フランス","クロアチア","ベルギー"),
    (2022,"アルゼンチン","フランス","クロアチア"),
]

def fetch_live_odds():
    """DB保存のオッズ一覧を返す（オッズ順ソート）"""
    cfg = get_odds_config()
    odds_list = sorted(
        [{'name': t, 'odds': cfg.get(t, o)} for t, o in TEAMS_WITH_ODDS],
        key=lambda x: x['odds']
    )
    return {'odds': odds_list, 'updated_at': '', 'source': '参考オッズ'}

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

def score_prediction(b, r1, r2, r3):
    """
    オッズ連動ポイント計算

    3連単（順番通り完全一致）
        → 1位オッズ × 2位オッズ × 3位オッズ  （掛け算）

    3連複（3チーム全員正解・順不同）
        → 1位オッズ + 2位オッズ + 3位オッズ  （足し算）

    単勝（1〜2チームがトップ3に入った）
        → 的中チームのオッズの合計            （足し算）
        ※ 3チーム全員は3連複扱いのため除く
    """
    top3 = {r1, r2, r3}
    my   = [b.team1, b.team2, b.team3]

    # 3連単：完全一致
    if b.team1 == r1 and b.team2 == r2 and b.team3 == r3:
        return get_team_odds(r1) * get_team_odds(r2) * get_team_odds(r3)

    # 3連複：3チーム全員正解（順不同）
    if set(filter(None, my)) == top3:
        return get_team_odds(r1) + get_team_odds(r2) + get_team_odds(r3)

    # 単勝：1〜2チーム正解 → 的中チームのオッズ合計
    return sum(get_team_odds(t) for t in my if t and t in top3)

def calc_stats():
    """表示用：予想の集計・重複チェック用"""
    bets = Bet.query.all()
    buy_in = get_cfg('buy_in', 3000)
    # 合計プール = 予想入力済み参加者数 × 現在の掛け金
    bet_count = len(bets)
    total_pool = bet_count * buy_in
    pred_count = {}
    for b in bets:
        key = f"{b.team1}|{b.team2}|{b.team3}"
        pred_count[key] = pred_count.get(key, 0) + 1
    return total_pool, pred_count

def payout_scenarios(participant):
    """
    自分の予想のオッズから3連単/3連複/単勝それぞれの推定ポイントと
    「自分だけ当たった場合」の最大配当を返す
    """
    if not participant.bets:
        return None
    b = participant.bets[0]
    all_bets = Bet.query.all()
    total_pool = sum(x.amount for x in all_bets)
    if total_pool == 0:
        return None

    o1 = get_team_odds(b.team1)
    o2 = get_team_odds(b.team2)
    o3 = get_team_odds(b.team3)

    pts_trifecta = round(o1 * o2 * o3, 1)
    pts_trio     = round(o1 + o2 + o3, 1)

    # 同じ予想の人数
    same_key   = f"{b.team1}|{b.team2}|{b.team3}"
    same_count = sum(1 for x in all_bets if f"{x.team1}|{x.team2}|{x.team3}" == same_key)

    scenarios = {
        f'3連単的中 ({pts_trifecta}pt)': round(pts_trifecta / (pts_trifecta * same_count) * total_pool) if same_count else total_pool,
        f'3連複的中 ({pts_trio}pt)': round(pts_trio / (pts_trio * same_count) * total_pool) if same_count else total_pool,
    }
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
    buy_in = get_cfg('buy_in', 3000)
    total_pool = len(all_bets) * buy_in

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
    # アクセスカウント（ボット除外のため簡易チェック）
    ua = request.headers.get('User-Agent', '')
    if 'bot' not in ua.lower() and 'crawl' not in ua.lower():
        count = get_cfg('page_views', 0)
        set_cfg('page_views', count + 1)

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
        first_match_time=get_cfg('first_match_time', '2026-06-12T02:00'),
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

@app.route('/odds')
def odds_list():
    participant = None
    if 'token' in session:
        participant = Participant.query.filter_by(token=session['token']).first()
    return render_template('odds_list.html',
        participant=participant,
        odds=[{'name': t, 'odds': o} for t, o in TEAMS_WITH_ODDS])

@app.route('/api/rakuten-odds')
def api_rakuten_odds():
    return jsonify(fetch_live_odds())

_news_cache = {'data': None, 'updated': None}

@app.route('/api/wc-news')
def api_wc_news():
    """W杯ニュースをGoogleニュースRSSから取得（30分キャッシュ）"""
    import xml.etree.ElementTree as ET
    import re as _re

    now = datetime.now(timezone.utc)
    if (_news_cache['data'] is not None and _news_cache['updated'] and
            now - _news_cache['updated'] < timedelta(minutes=30)):
        return jsonify(_news_cache['data'])

    try:
        url = 'https://news.google.com/rss/search?q=ワールドカップ2026+サッカー&hl=ja&gl=JP&ceid=JP:ja'
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=8) as res:
            xml_data = res.read().decode('utf-8', errors='replace')

        root = ET.fromstring(xml_data)
        channel = root.find('channel')
        items = channel.findall('item') if channel else []

        news = []
        for item in items[:10]:
            title = item.findtext('title', '')
            link  = item.findtext('link', '')
            pub   = item.findtext('pubDate', '')
            src_el = item.find('source')
            source = src_el.text if src_el is not None else ''

            # Google NewsのリダイレクトURLをそのまま使う
            # タイトルから「 - ソース名」部分を除去
            clean_title = _re.sub(r'\s*[-–]\s*[^-–]+$', '', title).strip()

            # 日時を日本語に変換
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub)
                jst = dt + timedelta(hours=9)
                pub_ja = jst.strftime('%m/%d %H:%M')
            except Exception:
                pub_ja = ''

            if clean_title and link:
                news.append({
                    'title': clean_title,
                    'link': link,
                    'source': source,
                    'pub': pub_ja,
                })

        result = {'news': news, 'updated_at': now.isoformat()}
        _news_cache['data'] = result
        _news_cache['updated'] = now
        return jsonify(result)

    except Exception as e:
        if _news_cache['data']:
            return jsonify(_news_cache['data'])
        return jsonify({'error': str(e), 'news': []})

@app.route('/api/wc-history')
def api_wc_history():
    return jsonify([{'year': y, 'first': f, 'second': s, 'third': t}
                    for y, f, s, t in WC_HISTORY])

@app.route('/api/simulate', methods=['POST'])
def simulate():
    """仮の結果を入力して全員の配当をシミュレーション"""
    data = request.json
    r1 = data.get('first', '').strip()
    r2 = data.get('second', '').strip()
    r3 = data.get('third', '').strip()
    if not r1 or not r2 or not r3:
        return jsonify({'error': '1位・2位・3位をすべて選択してください'}), 400
    if len({r1, r2, r3}) < 3:
        return jsonify({'error': '同じチームを選択できません'}), 400

    all_bets = Bet.query.all()
    buy_in = get_cfg('buy_in', 3000)
    total_pool = len(all_bets) * buy_in

    # 各参加者のポイントと判定を計算
    results_list = []
    for p in Participant.query.order_by(Participant.joined_at).all():
        if not p.bets:
            results_list.append({
                'name': p.name, 'pts': 0, 'payout': 0,
                'label': '未入力', 'team1': '--', 'team2': '--', 'team3': '--'
            })
            continue
        b = p.bets[0]
        pts = round(score_prediction(b, r1, r2, r3), 1)

        # 判定ラベル（オッズ連動表示）
        top3 = {r1, r2, r3}
        my = [b.team1, b.team2, b.team3]
        if b.team1 == r1 and b.team2 == r2 and b.team3 == r3:
            label = f'🥇 3連単 ({pts}pt)'
        elif set(filter(None, my)) == top3:
            label = f'🎯 3連複 ({pts}pt)'
        else:
            hit = sum(1 for t in my if t and t in top3)
            if hit > 0:
                label = f'✅ {hit}チーム的中 ({pts}pt)'
            else:
                label = '❌ ハズレ (0pt)'

        results_list.append({
            'name': p.name, 'pts': pts,
            'team1': b.team1, 'team2': b.team2, 'team3': b.team3,
            'label': label
        })

    total_pts = sum(r['pts'] for r in results_list)

    # 配当計算（余りなし）
    for r in results_list:
        r['payout'] = round(r['pts'] / total_pts * total_pool) if total_pts > 0 else 0

    # 端数調整
    if total_pts > 0:
        diff = total_pool - sum(r['payout'] for r in results_list)
        if diff != 0:
            top = max(results_list, key=lambda x: x['pts'])
            top['payout'] += diff

    results_list.sort(key=lambda x: (-x['pts'], x['name']))
    return jsonify({
        'results': results_list,
        'total_pool': total_pool,
        'total_pts': total_pts,
        'r1': r1, 'r2': r2, 'r3': r3
    })

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
            set_cfg('odds_api_key', request.form.get('odds_api_key', '').strip())
            _odds_cache['data'] = None  # キャッシュクリア
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
            set_cfg('first_match_time', request.form.get('first_match_time', '').strip())
            _match_cache['data'] = None
            _standings_cache['data'] = None

        elif action == 'update_odds':
            new_odds = {}
            for team, default_odds in TEAMS_WITH_ODDS:
                raw = request.form.get(f'odds_{team}', '').strip()
                try:
                    new_odds[team] = float(raw)
                except ValueError:
                    new_odds[team] = default_odds
            set_cfg('team_odds', new_odds)
            _odds_cache['data'] = None

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
        odds_api_key=get_cfg('odds_api_key', ''),
        deadline=get_cfg('deadline', ''),
        first_match_time=get_cfg('first_match_time', '2026-06-12T02:00'),
        odds_config=get_odds_config(),
        teams_with_odds=TEAMS_WITH_ODDS,
        is_open=get_cfg('is_open', True),
        total_pool=total_pool,
        page_views=get_cfg('page_views', 0),
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
