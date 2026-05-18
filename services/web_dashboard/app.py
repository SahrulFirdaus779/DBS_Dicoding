from flask import Flask, render_template, jsonify, request, abort
from flask_cors import CORS
import pandas as pd
import os, json, time
from pymongo import MongoClient
from datetime import datetime, timedelta

# ── Load .env ─────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────
MONGO_URI         = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
SECRET_KEY        = os.getenv("FLASK_SECRET_KEY", "zakatsight-dev")
CACHE_CLEAR_TOKEN = os.getenv("CACHE_CLEAR_TOKEN", "zakatsight-cache-token-2026")
FLASK_DEBUG       = os.getenv("FLASK_DEBUG", "true").lower() == "true"
FLASK_PORT        = int(os.getenv("FLASK_PORT", "5000"))
CORS_ORIGIN       = os.getenv("CORS_ORIGIN", "http://localhost:3000")
CACHE_TTL         = 300  # 5 menit

app = Flask(__name__)
app.secret_key = SECRET_KEY
CORS(app, origins=[CORS_ORIGIN])

# ── Rate limiting sederhana (in-memory) ───────────────────────
_rate_limit = {}
def check_rate_limit(key, max_calls=60, window=60):
    now = time.time()
    calls = [t for t in _rate_limit.get(key, []) if now - t < window]
    calls.append(now)
    _rate_limit[key] = calls
    return len(calls) <= max_calls

# ── Cache ─────────────────────────────────────────────────────
_cache = {
    'public_stats': {'data': None, 'timestamp': 0},
    'internal_stats': {}
}

# ── MongoDB ───────────────────────────────────────────────────
client = MongoClient(
    MONGO_URI,
    maxPoolSize=20,
    minPoolSize=2,
    serverSelectionTimeoutMS=5000
)
db              = client["zakatsight"]
col_penerimaan  = db["penerimaan"]
col_mustahiq    = db["mustahiq"]

# Ensure indexes
try:
    col_penerimaan.create_index([("tgl_dt", 1)])
    col_penerimaan.create_index([("channel", 1)])
    col_penerimaan.create_index([("program", 1)])
    col_penerimaan.create_index([("donatur", 1)])
    col_penerimaan.create_index([("tgl_dt", 1), ("channel", 1)])
    col_penerimaan.create_index([("tgl_dt", -1), ("channel", 1), ("kategori_program", 1)])
    
    col_mustahiq.create_index([("status_penyaluran", 1)])
    col_mustahiq.create_index([("kategori_asnaf", 1)])
    col_mustahiq.create_index([("tgl_dt", -1), ("channel", 1)])
    col_mustahiq.create_index([("nama_mustahiq", 1)])
    col_mustahiq.create_index([("program", 1)])
    col_mustahiq.create_index([("relawan", 1)])
    print("[OK] MongoDB optimal indexes ensured.")
except Exception as e:
    print(f"[WARN] Index creation skipped: {e}")

# ── Segmentation module (optional) ────────────────────────────
try:
    from segmentation import SegmentationModel
    BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
    seg_model = SegmentationModel(os.path.join(BASE_DIR, 'models'))
except Exception:
    seg_model = None

# ── Helpers ───────────────────────────────────────────────────
def format_rp(val):
    if val >= 1_000_000_000:
        return f"Rp {val/1_000_000_000:.1f}M"
    elif val >= 1_000_000:
        return f"Rp {val/1_000_000:.0f}jt"
    elif val >= 1_000:
        return f"Rp {val/1_000:.0f}rb"
    return f"Rp {int(val):,}"

MONTH_MAP = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'Mei',6:'Jun',
             7:'Jul',8:'Ags',9:'Sep',10:'Okt',11:'Nov',12:'Des'}

def validate_year_month(year, month):
    """Validasi dan sanitasi input year/month."""
    valid_years = ['all'] + [str(y) for y in range(2018, 2030)]
    valid_months = ['all'] + [str(m) for m in range(1, 13)]
    year  = year  if year  in valid_years  else 'all'
    month = month if month in valid_months else 'all'
    return year, month

def build_match(year, month, channel='all', category='all'):
    """Build MongoDB $match stage dari filter."""
    match = {}
    if year != 'all':
        y = int(year)
        if month != 'all':
            m = int(month)
            match["tgl_dt"] = {"$gte": datetime(y,m,1),
                                "$lt":  datetime(y,m+1,1) if m < 12 else datetime(y+1,1,1)}
        else:
            match["tgl_dt"] = {"$gte": datetime(y,1,1), "$lt": datetime(y+1,1,1)}
            
    if channel and channel != 'all':
        match["channel"] = channel
        
    if category and category != 'all':
        match["kategori_program"] = category
        
    return match

def etag_cached(f):
    """Decorator untuk mengimplementasikan HTTP ETag conditional GET caching."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        res = f(*args, **kwargs)
        if res.status_code == 200:
            import hashlib
            from flask import make_response
            content = res.get_data()
            etag_hash = f'"{hashlib.md5(content).hexdigest()}"'
            
            if_none_match = request.headers.get("If-None-Match")
            if if_none_match and if_none_match == etag_hash:
                resp = make_response("", 304)
                resp.headers["ETag"] = etag_hash
                return resp
                
            res.headers["ETag"] = etag_hash
        return res
    return decorated_function

# ─────────────────────────────────────────────────────────────
# DASHBOARD INTERNAL
# ─────────────────────────────────────────────────────────────
def get_dashboard_stats(year='all', month='all', channel='all', category='all'):
    match = build_match(year, month, channel, category)
    pipeline = [{"$match": match}] if match else []

    stats = {
        'total_nominal': 0, 'jumlah_transaksi': 0, 'donatur_unik': 0,
        'rata_rata_donasi': 0, 'total_nominal_str': 'Rp 0',
        'rata_rata_donasi_str': 'Rp 0', 'bulan_tertinggi_nama': '-',
        'bulan_tertinggi_val': 'Rp 0',
        'monthly_labels': [], 'monthly_data': [],
        'channel_labels': [], 'channel_data': [],
        'bank_labels': [], 'bank_data': [],
        'distribusi_labels': [], 'distribusi_data': [],
        'latest_txns': []
    }

    # 1. KPI
    kpi_res = list(col_penerimaan.aggregate(pipeline + [
        {"$group": {
            "_id": None,
            "total_nominal":   {"$sum": "$nominal"},
            "jumlah_transaksi":{"$sum": 1}
        }}
    ]))
    if kpi_res:
        kpi = kpi_res[0]
        stats['total_nominal']    = kpi['total_nominal']
        stats['jumlah_transaksi'] = kpi['jumlah_transaksi']
        if kpi['jumlah_transaksi'] > 0:
            stats['rata_rata_donasi'] = kpi['total_nominal'] / kpi['jumlah_transaksi']
        stats['total_nominal_str']   = format_rp(stats['total_nominal'])
        stats['rata_rata_donasi_str']= format_rp(stats['rata_rata_donasi'])

    # donatur_unik via distinct (lebih efisien dari addToSet)
    try:
        filter_q = match if match else {}
        stats['donatur_unik'] = len(col_penerimaan.distinct("donatur", filter_q))
    except Exception:
        stats['donatur_unik'] = 0

    # 2. Trend — 3 level
    if year == 'all':
        agg = pipeline + [
            {"$match": {"tgl_dt": {"$ne": None}}},
            {"$group": {"_id": {"year":{"$year":"$tgl_dt"}}, "nominal":{"$sum":"$nominal"}}},
            {"$sort": {"_id.year": 1}}
        ]
        res = list(col_penerimaan.aggregate(agg))
        if res:
            peak = max(res, key=lambda x: x['nominal'])
            stats['bulan_tertinggi_nama'] = f"Tahun {peak['_id']['year']}"
            stats['bulan_tertinggi_val']  = format_rp(peak['nominal'])
            for r in res:
                stats['monthly_labels'].append(str(r['_id']['year']))
                stats['monthly_data'].append(round(r['nominal']/1_000_000, 2))

    elif month == 'all':
        agg = pipeline + [
            {"$match": {"tgl_dt": {"$ne": None}}},
            {"$group": {"_id": {"year":{"$year":"$tgl_dt"},"month":{"$month":"$tgl_dt"}}, "nominal":{"$sum":"$nominal"}}},
            {"$sort": {"_id.year": 1, "_id.month": 1}}
        ]
        res = list(col_penerimaan.aggregate(agg))
        if res:
            peak = max(res, key=lambda x: x['nominal'])
            stats['bulan_tertinggi_nama'] = f"{MONTH_MAP.get(peak['_id']['month'],'')} {peak['_id']['year']}"
            stats['bulan_tertinggi_val']  = format_rp(peak['nominal'])
            for r in res:
                stats['monthly_labels'].append(f"{MONTH_MAP.get(r['_id']['month'],'')} {r['_id']['year']}")
                stats['monthly_data'].append(round(r['nominal']/1_000_000, 2))
    else:
        agg = pipeline + [
            {"$match": {"tgl_dt": {"$ne": None}}},
            {"$group": {"_id": {"year":{"$year":"$tgl_dt"},"month":{"$month":"$tgl_dt"},"day":{"$dayOfMonth":"$tgl_dt"}}, "nominal":{"$sum":"$nominal"}}},
            {"$sort": {"_id.year": 1, "_id.month": 1, "_id.day": 1}}
        ]
        res = list(col_penerimaan.aggregate(agg))
        if res:
            peak = max(res, key=lambda x: x['nominal'])
            stats['bulan_tertinggi_nama'] = f"{peak['_id']['day']:02d} {MONTH_MAP.get(peak['_id']['month'],'')}"
            stats['bulan_tertinggi_val']  = format_rp(peak['nominal'])
            for r in res:
                stats['monthly_labels'].append(f"{r['_id']['day']:02d}")
                stats['monthly_data'].append(round(r['nominal']/1_000_000, 2))

    # 3. Channel
    for c in col_penerimaan.aggregate(pipeline + [
        {"$group": {"_id": "$channel", "nominal": {"$sum": "$nominal"}}},
        {"$sort": {"nominal": -1}}, {"$limit": 8}
    ]):
        stats['channel_labels'].append(str(c['_id']) if c['_id'] else 'Unknown')
        stats['channel_data'].append(round(c['nominal']/1_000_000, 2))

    # 4. Bank
    bank_res = list(col_penerimaan.aggregate(pipeline + [
        {"$group": {"_id": "$bank", "nominal": {"$sum": "$nominal"}}},
        {"$sort": {"nominal": -1}}
    ]))
    total_bank = sum(b['nominal'] for b in bank_res) or 1
    for b in bank_res[:4]:
        stats['bank_labels'].append(str(b['_id'])[:15] if b['_id'] else 'Unknown')
        stats['bank_data'].append(round((b['nominal']/total_bank)*100, 1))
    others = sum(b['nominal'] for b in bank_res[4:])
    if others > 0:
        stats['bank_labels'].append('Lainnya')
        stats['bank_data'].append(round((others/total_bank)*100, 1))

    # 5. Distribusi Kategori (dari program field — BUKAN hardcoded)
    dist_res = list(col_penerimaan.aggregate(pipeline + [
        {"$group": {"_id": "$program", "nominal": {"$sum": "$nominal"}}},
        {"$sort": {"nominal": -1}}, {"$limit": 6}
    ]))
    total_prog = sum(d['nominal'] for d in dist_res) or 1
    for d in dist_res:
        nama = str(d['_id'])[:20] if d['_id'] else 'Lainnya'
        stats['distribusi_labels'].append(nama)
        stats['distribusi_data'].append(round((d['nominal']/total_prog)*100, 1))

    # 6. Latest Transactions
    for txn in col_penerimaan.aggregate(pipeline + [
        {"$sort": {"tgl_dt": -1}}, {"$limit": 10}
    ]):
        tgl = txn['tgl_dt'].strftime('%d %b %Y') if txn.get('tgl_dt') else '-'
        stats['latest_txns'].append({
            'donatur': str(txn.get('donatur','Hamba Allah'))[:20],
            'nominal': format_rp(txn.get('nominal', 0)),
            'program': str(txn.get('program','-'))[:25],
            'channel': str(txn.get('channel','-'))[:20],
            'tgl': tgl
        })

    return stats

# ─────────────────────────────────────────────────────────────
# PUBLIC STATS
# ─────────────────────────────────────────────────────────────
def get_public_stats():
    stats = {
        'total_terkumpul_str':'Rp 0','total_disalurkan_str':'Rp 0',
        'progress_percent':0,'keluarga_terbantu':0,'program_aktif':0,
        'titik_wilayah':0,'distribusi_labels':[],'distribusi_data':[],
        'latest_donations':[]
    }
    kpi = list(col_penerimaan.aggregate([{"$group":{"_id":None,"total":{"$sum":"$nominal"}}}]))
    if kpi:
        stats['total_terkumpul_str'] = format_rp(kpi[0]['total'])
    dist = list(col_mustahiq.aggregate([
        {"$match":{"status_penyaluran":"Tersalurkan"}},
        {"$group":{"_id":None,"total":{"$sum":"$nominal_disalurkan"}}}
    ]))
    total_dis = dist[0]['total'] if dist else 0
    stats['total_disalurkan_str'] = format_rp(total_dis)
    total_kum = kpi[0]['total'] if kpi else 1
    stats['progress_percent'] = round((total_dis/total_kum)*100) if total_kum else 0
    try:
        stats['keluarga_terbantu'] = len(col_mustahiq.distinct('mustahiq_id'))
        stats['program_aktif']     = len(col_mustahiq.distinct('program'))
        stats['titik_wilayah']     = len(col_mustahiq.distinct('channel'))
    except Exception: pass
    dist_res = list(col_mustahiq.aggregate([
        {"$match":{"status_penyaluran":"Tersalurkan"}},
        {"$group":{"_id":"$kategori_asnaf","nominal":{"$sum":"$nominal_disalurkan"}}},
        {"$sort":{"nominal":-1}},{"$limit":6}
    ]))
    for d in dist_res:
        asnaf = str(d.get('_id','Lainnya')) or 'Lainnya'
        pct   = round((d['nominal']/total_dis)*100,1) if total_dis else 0
        stats['distribusi_labels'].append(asnaf)
        stats['distribusi_data'].append(pct)
    for txn in col_penerimaan.aggregate([{"$sort":{"tgl_dt":-1}},{"$limit":10}]):
        tgl = txn['tgl_dt'].strftime('%d %b %Y') if txn.get('tgl_dt') else '-'
        stats['latest_donations'].append({
            'donatur':'Hamba Allah',
            'nominal': format_rp(txn.get('nominal',0)),
            'program': str(txn.get('program','Zakat'))[:20],
            'waktu':   tgl
        })
    return stats

def cached(key, fn, ttl=CACHE_TTL):
    now = time.time()
    item = _cache['internal_stats'].get(key)
    if item and now - item['timestamp'] < ttl:
        return item['data']
    data = fn()
    _cache['internal_stats'][key] = {'data': data, 'timestamp': now}
    return data

# ─────────────────────────────────────────────────────────────
# ANALYTICS ENDPOINTS
# ─────────────────────────────────────────────────────────────
def analytics_donatur(year='all', month='all', channel='all', category='all'):
    match = build_match(year, month, channel, category)
    filter_q = match if match else {}

    # KPI
    kpi = list(col_penerimaan.aggregate([
        {"$match": filter_q} if filter_q else {"$match": {}},
        {"$group": {"_id": None, "total_nominal": {"$sum":"$nominal"}, "total_txn":{"$sum":1}}}
    ]))
    total_donatur = len(col_penerimaan.distinct("donatur", filter_q))

    # Donatur aktif 90 hari terakhir
    cutoff_90 = datetime.now() - timedelta(days=90)
    active_90  = len(col_penerimaan.distinct("donatur", {"tgl_dt": {"$gte": cutoff_90}}))

    # Rata-rata frekuensi donasi per donatur
    freq_agg = list(col_penerimaan.aggregate([
        {"$match": filter_q} if filter_q else {"$match": {}},
        {"$group": {"_id": "$donatur", "freq": {"$sum": 1}}},
        {"$group": {"_id": None, "avg_freq": {"$avg": "$freq"}}}
    ]))
    avg_freq = round(freq_agg[0]['avg_freq'], 1) if freq_agg else 0

    # Top 10 donatur
    top_donatur = list(col_penerimaan.aggregate([
        {"$match": filter_q} if filter_q else {"$match": {}},
        {"$group": {"_id": "$donatur", "total": {"$sum":"$nominal"}, "frekuensi": {"$sum":1}}},
        {"$sort": {"total": -1}},
        {"$limit": 10}
    ]))

    # RFM Segmentation (simplified dari data riil)
    # Champions: freq >= 5, total >= 1jt
    # Loyal: freq >= 3
    # Potential: freq = 2
    # At-Risk: freq = 1, last txn > 90 hari
    # Lost: last txn > 180 hari
    rfm_raw = list(col_penerimaan.aggregate([
        {"$group": {
            "_id": "$donatur",
            "total": {"$sum":"$nominal"},
            "freq":  {"$sum": 1},
            "last_txn": {"$max": "$tgl_dt"}
        }},
        {"$limit": 50000}
    ]))
    now_dt = datetime.now()
    segments = {"Champions":0,"Loyal":0,"Potential Loyalist":0,"At-Risk":0,"Lost":0}
    for r in rfm_raw:
        freq  = r['freq']
        total = r['total']
        last  = r.get('last_txn')
        days_ago = (now_dt - last).days if last else 9999
        if freq >= 5 and total >= 1_000_000:
            segments["Champions"] += 1
        elif freq >= 3:
            segments["Loyal"] += 1
        elif freq == 2:
            segments["Potential Loyalist"] += 1
        elif days_ago > 180:
            segments["Lost"] += 1
        else:
            segments["At-Risk"] += 1

    total_seg = sum(segments.values()) or 1

    # Distribusi frekuensi
    freq_dist = list(col_penerimaan.aggregate([
        {"$match": filter_q} if filter_q else {"$match": {}},
        {"$group": {"_id": "$donatur", "freq": {"$sum": 1}}},
        {"$group": {"_id": "$freq", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
        {"$limit": 10}
    ]))

    return {
        "total_donatur": total_donatur,
        "donatur_aktif_90": active_90,
        "avg_freq": avg_freq,
        "top_donatur": [
            {"nama": str(d['_id'])[:20] if d['_id'] else "Hamba Allah",
             "total_str": format_rp(d['total']), "frekuensi": d['frekuensi']}
            for d in top_donatur
        ],
        "rfm_segments": [
            {"seg": k, "count": v, "pct": round((v/total_seg)*100, 1)}
            for k, v in segments.items()
        ],
        "freq_labels": [str(f['_id'])+"x" for f in freq_dist],
        "freq_data":   [f['count'] for f in freq_dist],
    }

def analytics_program(year='all', month='all', channel='all', category='all'):
    match = build_match(year, month, channel, category)
    filter_q = match if match else {}
    programs = list(col_penerimaan.aggregate([
        {"$match": filter_q} if filter_q else {"$match": {}},
        {"$group": {"_id": "$program", "total": {"$sum":"$nominal"}, "txn": {"$sum":1}}},
        {"$sort": {"total": -1}},
        {"$limit": 12}
    ]))
    total_all = sum(p['total'] for p in programs) or 1
    max_val   = programs[0]['total'] if programs else 1
    return {
        "total_nominal": total_all,
        "programs": [
            {"name": str(p['_id'])[:30] if p['_id'] else "Lainnya",
             "total_str": format_rp(p['total']), "total_raw": p['total'],
             "txn": p['txn'],
             "pct_total": round((p['total']/total_all)*100, 1),
             "pct_max":   round((p['total']/max_val)*100, 1)}
            for p in programs
        ]
    }

def analytics_relawan(year='all', month='all', channel='all', category='all'):
    match = build_match(year, month, channel, category)
    filter_q = match if match else {}
    
    # Leaderboard Channel
    channels = list(col_penerimaan.aggregate([
        {"$match": filter_q} if filter_q else {"$match": {}},
        {"$group": {"_id": "$channel", "total": {"$sum":"$nominal"}, "txn": {"$sum":1}}},
        {"$sort": {"total": -1}},
        {"$limit": 15}
    ]))
    total_all_channel = sum(c['total'] for c in channels) or 1
    
    # Leaderboard Relawan
    volunteers = list(col_penerimaan.aggregate([
        {"$match": filter_q} if filter_q else {"$match": {}},
        {"$group": {
            "_id": "$relawan",
            "kode": {"$first": "$kode_relawan"},
            "channel": {"$first": "$channel"},
            "total": {"$sum": "$nominal"},
            "txn": {"$sum": 1}
        }},
        {"$sort": {"total": -1}},
        {"$limit": 15}
    ]))
    total_all_vol = sum(v['total'] for v in volunteers) or 1
    
    # Total unique volunteers active under this filter
    try:
        total_relawan = len(col_penerimaan.distinct("relawan", filter_q))
    except Exception:
        total_relawan = 0
        
    return {
        "total_channel": len(channels),
        "total_relawan": total_relawan,
        "leaderboard": [
            {"rank": i+1,
             "nama": str(c['_id'])[:25] if c['_id'] else "Unknown",
             "total_str": format_rp(c['total']), "txn": c['txn'],
             "pct": round((c['total']/total_all_channel)*100, 1)}
            for i, c in enumerate(channels)
        ],
        "leaderboard_relawan": [
            {"rank": i+1,
             "nama": str(v['_id'])[:25] if v['_id'] else "Unknown",
             "kode": str(v['kode']) if v.get('kode') else "-",
             "channel": str(v['channel'])[:20] if v.get('channel') else "-",
             "total_str": format_rp(v['total']), "txn": v['txn'],
             "pct": round((v['total']/total_all_vol)*100, 1)}
            for i, v in enumerate(volunteers)
        ]
    }

# ─────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────
@app.before_request
def rate_limit_check():
    ip = request.remote_addr or "unknown"
    if not check_rate_limit(ip, max_calls=120, window=60):
        return jsonify({"error": "Rate limit exceeded"}), 429

@app.route('/api/v1/public/stats')
def api_public_stats():
    now = time.time()
    if _cache['public_stats']['data'] and now - _cache['public_stats']['timestamp'] < CACHE_TTL:
        return jsonify(_cache['public_stats']['data'])
    data = get_public_stats()
    _cache['public_stats'] = {'data': data, 'timestamp': now}
    return jsonify(data)

@app.route('/api/dashboard')
@etag_cached
def api_dashboard():
    year, month = validate_year_month(request.args.get('year','all'), request.args.get('month','all'))
    channel = request.args.get('channel', 'all')
    category = request.args.get('category', 'all')
    cache_key = f"dash_{year}_{month}_{channel}_{category}"
    return jsonify(cached(cache_key, lambda: get_dashboard_stats(year, month, channel, category)))

@app.route('/api/analytics/donatur')
@etag_cached
def api_analytics_donatur():
    year, month = validate_year_month(request.args.get('year','all'), request.args.get('month','all'))
    channel = request.args.get('channel', 'all')
    category = request.args.get('category', 'all')
    key = f"donatur_{year}_{month}_{channel}_{category}"
    return jsonify(cached(key, lambda: analytics_donatur(year, month, channel, category)))

@app.route('/api/analytics/program')
@etag_cached
def api_analytics_program():
    year, month = validate_year_month(request.args.get('year','all'), request.args.get('month','all'))
    channel = request.args.get('channel', 'all')
    category = request.args.get('category', 'all')
    key = f"program_{year}_{month}_{channel}_{category}"
    return jsonify(cached(key, lambda: analytics_program(year, month, channel, category)))

@app.route('/api/analytics/relawan')
@etag_cached
def api_analytics_relawan():
    year, month = validate_year_month(request.args.get('year','all'), request.args.get('month','all'))
    channel = request.args.get('channel', 'all')
    category = request.args.get('category', 'all')
    key = f"relawan_{year}_{month}_{channel}_{category}"
    return jsonify(cached(key, lambda: analytics_relawan(year, month, channel, category)))

# ── Analytics Penerima Manfaat (Mustahiq) ──────────────────────
def analytics_penerima(year='all', month='all', channel='all', category='all'):
    match = build_match(year, month, channel, category)
    pipeline = [{"$match": match}] if match else []

    # 1. Total Mustahiq (distinct mustahiq_id)
    try:
        filter_q = match if match else {}
        total_mustahiq = len(col_mustahiq.distinct("mustahiq_id", filter_q))
    except Exception:
        total_mustahiq = 0

    # 2. Total nominal disalurkan & avg & count
    nominal_res = list(col_mustahiq.aggregate(pipeline + [
        {"$group": {
            "_id": None,
            "total_disalurkan": {"$sum": "$nominal_disalurkan"},
            "avg_disalurkan": {"$avg": "$nominal_disalurkan"},
            "count": {"$sum": 1}
        }}
    ]))

    total_disalurkan = 0
    avg_disalurkan = 0
    if nominal_res:
        total_disalurkan = nominal_res[0].get('total_disalurkan', 0) or 0
        avg_disalurkan = nominal_res[0].get('avg_disalurkan', 0) or 0

    # 3. Status Penyaluran breakdown
    status_res = list(col_mustahiq.aggregate(pipeline + [
        {"$group": {"_id": "$status_penyaluran", "count": {"$sum": 1}}}
    ]))
    status_breakdown = {s['_id'] or "Unknown": s['count'] for s in status_res}
    total_tx = sum(status_breakdown.values()) or 1
    tersalurkan_count = status_breakdown.get("Tersalurkan", 0)
    pct_tersalurkan = round((tersalurkan_count / total_tx) * 100, 1)

    # 4. Sebaran Asnaf (nominal)
    asnaf_res = list(col_mustahiq.aggregate(pipeline + [
        {"$group": {"_id": "$kategori_asnaf", "nominal": {"$sum": "$nominal_disalurkan"}}},
        {"$sort": {"nominal": -1}},
        {"$limit": 6}
    ]))
    asnaf_labels = [str(a['_id']) if a['_id'] else 'Lainnya' for a in asnaf_res]
    asnaf_data = [round(a['nominal']/1_000_000, 2) for a in asnaf_res]

    # 5. Sebaran Wilayah / Channel (nominal)
    wilayah_res = list(col_mustahiq.aggregate(pipeline + [
        {"$group": {"_id": "$channel", "nominal": {"$sum": "$nominal_disalurkan"}}},
        {"$sort": {"nominal": -1}},
        {"$limit": 8}
    ]))
    wilayah_labels = [str(w['_id'])[:15] if w['_id'] else 'Lainnya' for w in wilayah_res]
    wilayah_data = [round(w['nominal']/1_000_000, 2) for w in wilayah_res]

    return {
        "total_mustahiq": total_mustahiq,
        "total_disalurkan_str": format_rp(total_disalurkan),
        "avg_disalurkan_str": format_rp(avg_disalurkan),
        "pct_tersalurkan": pct_tersalurkan,
        "asnaf_labels": asnaf_labels,
        "asnaf_data": asnaf_data,
        "wilayah_labels": wilayah_labels,
        "wilayah_data": wilayah_data
    }

@app.route('/api/filters')
@etag_cached
def api_filters():
    channels = sorted([c for c in col_penerimaan.distinct("channel") if c])
    categories = sorted([c for c in col_penerimaan.distinct("kategori_program") if c])
    return jsonify({
        "channels": channels,
        "categories": categories
    })

@app.route('/api/analytics/penerima')
@etag_cached
def api_analytics_penerima():
    year, month = validate_year_month(request.args.get('year','all'), request.args.get('month','all'))
    channel = request.args.get('channel', 'all')
    category = request.args.get('category', 'all')
    key = f"penerima_{year}_{month}_{channel}_{category}"
    return jsonify(cached(key, lambda: analytics_penerima(year, month, channel, category)))

@app.route('/api/penerima/list')
def api_penerima_list():
    year, month = validate_year_month(request.args.get('year','all'), request.args.get('month','all'))
    channel = request.args.get('channel', 'all')
    category = request.args.get('category', 'all')
    page = max(1, int(request.args.get('page', 1)))
    limit = min(50, int(request.args.get('limit', 10)))
    search = request.args.get('search', '').strip()

    match = build_match(year, month, channel, category)
    if search:
        match["$or"] = [
            {"nama_mustahiq": {"$regex": search, "$options": "i"}},
            {"mustahiq_id": {"$regex": search, "$options": "i"}},
            {"program": {"$regex": search, "$options": "i"}},
            {"relawan": {"$regex": search, "$options": "i"}},
            {"channel": {"$regex": search, "$options": "i"}},
        ]

    total = col_mustahiq.count_documents(match)
    cursor = col_mustahiq.find(match).sort("tgl_dt", -1).skip((page-1)*limit).limit(limit)

    items = []
    for doc in cursor:
        tgl = doc['tgl_dt'].strftime('%d %b %Y') if doc.get('tgl_dt') else '-'
        items.append({
            'mustahiq_id': doc.get('mustahiq_id', '-'),
            'nama': doc.get('nama_mustahiq', doc.get('nama', 'Penerima Manfaat')),
            'asnaf': doc.get('kategori_asnaf', '-'),
            'program': doc.get('program', '-'),
            'nominal': format_rp(doc.get('nominal_disalurkan', 0)),
            'status': doc.get('status_penyaluran', 'Pending'),
            'channel': doc.get('channel', '-'),
            'relawan': doc.get('relawan', '-'),
            'tgl': tgl
        })

    return jsonify({
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit
    })

@app.route('/api/cache/clear', methods=['POST'])
def api_cache_clear():
    # Lindungi dengan token
    token = request.headers.get('X-Cache-Token') or request.json.get('token','') if request.is_json else ''
    if token != CACHE_CLEAR_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401
    _cache['public_stats'] = {'data': None, 'timestamp': 0}
    _cache['internal_stats'] = {}
    return jsonify({"status": "ok", "message": "Cache cleared"})

@app.route('/api/dashboard/txns')
def api_dashboard_txns():
    """Endpoint paginated untuk tabel transaksi."""
    year, month = validate_year_month(request.args.get('year','all'), request.args.get('month','all'))
    channel = request.args.get('channel', 'all')
    category = request.args.get('category', 'all')
    page   = max(1, int(request.args.get('page', 1)))
    limit  = min(50, int(request.args.get('limit', 10)))
    search = request.args.get('search', '').strip()

    match = build_match(year, month, channel, category)
    if search:
        match["$or"] = [
            {"donatur":  {"$regex": search, "$options": "i"}},
            {"program":  {"$regex": search, "$options": "i"}},
            {"channel":  {"$regex": search, "$options": "i"}},
        ]

    total = col_penerimaan.count_documents(match)
    cursor = col_penerimaan.find(match).sort("tgl_dt", -1).skip((page-1)*limit).limit(limit)

    txns = []
    for txn in cursor:
        tgl = txn['tgl_dt'].strftime('%d %b %Y') if txn.get('tgl_dt') else '-'
        txns.append({
            'donatur': str(txn.get('donatur','Hamba Allah'))[:20],
            'nominal': format_rp(txn.get('nominal',0)),
            'program': str(txn.get('program','-'))[:25],
            'channel': str(txn.get('channel','-'))[:20],
            'tgl': tgl
        })

    return jsonify({
        "txns": txns,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit
    })

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/transparansi')
def public_dashboard():
    return render_template('public.html')

@app.route('/api/forecast/kpis')
@etag_cached
def api_forecast_kpis():
    """Mengambil hasil forecasting dari FastAPI dan merangkumnya menjadi KPI harian, mingguan, bulanan, tahunan."""
    import requests
    
    FORECAST_URL = "http://localhost:8000"
    
    # 1. Harian (Esok)
    daily_pred = 0
    try:
        r_daily = requests.post(f"{FORECAST_URL}/forecast/tomorrow", json={}, timeout=3)
        if r_daily.ok:
            data = r_daily.json()
            daily_pred = data.get("forecast", {}).get("predicted_rupiah", 0)
    except Exception as e:
        print(f"[WARN] Failed to fetch daily forecast: {e}")
        
    # 2. Mingguan (7 Hari), Bulanan (30 Hari), Tahunan (30 Hari -> di-annualize)
    weekly_pred = 0
    monthly_pred = 0
    yearly_pred = 0
    try:
        # Forecast 30 hari sekaligus agar cepat dan efisien (timeout ditingkatkan menjadi 15s)
        r_range = requests.post(f"{FORECAST_URL}/forecast/range", json={"n_days": 30}, timeout=15)
        if r_range.ok:
            data = r_range.json()
            forecasts = data.get("forecasts", [])
            
            # Mingguan = sum 7 hari pertama
            weekly_pred = sum(f.get("predicted_rupiah", 0) for f in forecasts[:7])
            
            # Bulanan = sum 30 hari pertama
            monthly_pred = sum(f.get("predicted_rupiah", 0) for f in forecasts[:30])
            
            # Tahunan = annualized dari average daily nominal
            avg_daily = data.get("avg_daily_rupiah", 0)
            yearly_pred = avg_daily * 365
    except Exception as e:
        print(f"[WARN] Failed to fetch range forecast: {e}")
        
    return jsonify({
        "harian": format_rp(daily_pred),
        "harian_raw": daily_pred,
        "mingguan": format_rp(weekly_pred),
        "mingguan_raw": weekly_pred,
        "bulanan": format_rp(monthly_pred),
        "bulanan_raw": monthly_pred,
        "tahunan": format_rp(yearly_pred),
        "tahunan_raw": yearly_pred,
    })

if __name__ == '__main__':
    app.run(debug=FLASK_DEBUG, port=FLASK_PORT)
