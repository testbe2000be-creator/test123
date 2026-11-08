"""每日抓 FinMind 資料 -> 篩選 -> 輸出 data.json。需環境變數 FINMIND_TOKEN（建議）。"""
import os, sys, time, json, datetime as dt
import requests

API = "https://api.finmindtrade.com/api/v4/data"
TOKEN = os.getenv("FINMIND_TOKEN", "")
# 觀察名單：免費額度有限，先掃這份清單，可自行增減
WATCHLIST = ["2330","2454","2308","2382","3231","3017","9910","3443","6669","1519",
             "1503","2317","2303","3711","2357","2379","3034","2412","2881","2882",
             "2603","2301","2327","3008","2345","6415","3037","2368","3661","2376"]
TW = dt.timezone(dt.timedelta(hours=8))
today = dt.datetime.now(TW).date()
ago = lambda d: (today - dt.timedelta(days=d)).isoformat()

def get(dataset, sid=None, start=None):
    p = {"dataset": dataset}
    if sid: p["data_id"] = sid
    if start: p["start_date"] = start
    if TOKEN: p["token"] = TOKEN
    for i in range(3):
        try:
            j = requests.get(API, params=p, timeout=30).json()
            if j.get("status") == 200:
                time.sleep(0.25); return j["data"]
            print("API 回應異常", dataset, sid, j.get("msg"), file=sys.stderr)
        except Exception as e:
            print("請求失敗", dataset, sid, e, file=sys.stderr)
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"{dataset} {sid} 抓取失敗")

def analyze(sid, info):
    px = get("TaiwanStockPrice", sid, ago(130))
    if len(px) < 61: return None
    close = [r["close"] for r in px]
    ma60 = sum(close[-60:]) / 60
    last = close[-1]
    avg_vol = sum(r["Trading_Volume"] for r in px[-20:]) / 20 / 1000  # 股 -> 張
    rev = get("TaiwanStockMonthRevenue", sid, ago(600))
    m = {(r["revenue_year"], r["revenue_month"]): r["revenue"] for r in rev}
    yoy = []
    for y, mo in sorted(m)[-6:]:
        prev = m.get((y - 1, mo))
        if not prev: return None
        yoy.append(round((m[(y, mo)] / prev - 1) * 100, 1))
    if len(yoy) < 6: return None
    # 篩選條件：近6月 YOY 至少5個月 > 0、收盤 > 季線、20日均量 >= 500 張
    if not (sum(v > 0 for v in yoy) >= 5 and last > ma60 and avg_vol >= 500): return None

    ins = get("TaiwanStockInstitutionalInvestorsBuySell", sid, ago(40))
    net = {}
    for r in ins: net[r["date"]] = net.get(r["date"], 0) + r["buy"] - r["sell"]
    cl = {r["date"]: r["close"] for r in px}
    vals = [net[d] * cl[d] / 1e8 for d in sorted(net) if d in cl]  # 約略買賣超金額（億元）
    b5 = p5 = quad = None
    if len(vals) >= 10:
        b5, p5 = sum(vals[-5:]), sum(vals[-10:-5])
        quad = (1 if b5 >= p5 else 2) if b5 >= 0 else (3 if b5 >= p5 else 4)

    per = get("TaiwanStockPER", sid, ago(10))
    pe = yld = None
    if per:
        pe = per[-1].get("PER") or None
        yld = per[-1].get("dividend_yield")
    r2 = lambda x: None if x is None else round(x, 2)
    return {"code": sid, "name": info["name"], "industry": info["industry"],
            "close": r2(last), "ma60": r2(ma60), "bias": r2((last / ma60 - 1) * 100),
            "yoy": yoy, "yoy_avg": round(sum(yoy) / 6, 1), "avg_vol": round(avg_vol),
            "buy5": r2(b5), "buy5_prev": r2(p5), "quadrant": quad,
            "pe": r2(pe), "yield": r2(yld)}, cl

def main():
    info = {}
    for r in get("TaiwanStockInfo"):
        info.setdefault(r["stock_id"], {"name": r["stock_name"], "industry": r["industry_category"]})
    out, last_date = [], ""
    for sid in WATCHLIST:
        if sid not in info: continue
        try:
            res = analyze(sid, info[sid])
        except Exception as e:
            print("略過", sid, e, file=sys.stderr); continue
        if res:
            out.append(res[0]); last_date = max(last_date, max(res[1]))
    if not out and not last_date:
        sys.exit("沒有任何結果，保留舊的 data.json")
    out.sort(key=lambda x: -x["yoy_avg"])
    meta = {"updated": dt.datetime.now(TW).strftime("%Y-%m-%d %H:%M"),
            "data_date": last_date, "scanned": len(WATCHLIST), "passed": len(out), "sample": False}
    json.dump({"meta": meta, "stocks": out}, open("data.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("完成", meta)

if __name__ == "__main__": main()
