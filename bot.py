import hmac
import hashlib
import time
import json
import urllib.request
from datetime import datetime

# ==========================================
# API & STRATEGY CONFIGURATION
# ==========================================
API_KEY = "2kIzG51ahbDzAjHM2ivF4mRnVrwGBm"
API_SECRET = "yC9RTqantTOSKATmPvKdmQGGETu8GMM2bwxfFggrXoh9oUelVHPkkEqMqbIl"

TESTNET_BASE_URL = "https://testnet-api.delta.exchange"
PUBLIC_BASE_URL = "https://api.india.delta.exchange"

# आपका Google Apps Script Web App URL
GOOGLE_SHEET_WEB_URL = "https://script.google.com/macros/s/AKfycbyXcusyWMj8aJMsTzQbmcuTc_8THIJG-_TbazJGHIjIibTHyJeM4enJZIi2Cb0XxgQZbA/exec"

SYMBOL = "BTCUSD"
PRODUCT_ID = 27

INITIAL_CAPITAL = 10000.0
CURRENT_CAPITAL = 10000.0
BASE_QTY = 0.005
STEP_AMOUNT = 1000.0
QTY_INCREMENT = 0.005

BUFFER_POINTS = 200.0
INITIAL_SL_POINTS = 1000.0
FIXED_TP_POINTS = 2000.0
TRAILING_TRIGGER = 1000.0
TRAILING_DISTANCE = 800.0
REENTRY_GAP = 1000.0


def log_trade_to_sheet(trade_data):
    try:
        req = urllib.request.Request(
            GOOGLE_SHEET_WEB_URL,
            data=json.dumps(trade_data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            print("-> [Google Sheet] ट्रेड डेटा सफलतापूर्वक सेव हो गया!")
    except Exception as e:
        print(f"-> [Google Sheet Error]: {e}")


def get_signature(secret, method, path, payload=''):
    timestamp = str(int(time.time()))
    message = timestamp + method + path + payload
    signature = hmac.new(
        secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256
    ).hexdigest()
    return timestamp, signature


def send_signed_request(method, endpoint, data_dict=None):
    path = '/v2' + endpoint
    url = TESTNET_BASE_URL + path
    payload = json.dumps(data_dict) if data_dict else ''
    timestamp, signature = get_signature(API_SECRET, method, path, payload)

    headers = {
        'api-key': API_KEY,
        'timestamp': timestamp,
        'signature': signature,
        'Content-Type': 'application/json',
        'User-Agent': 'PythonBot',
    }

    try:
        req = urllib.request.Request(
            url,
            data=payload.encode('utf-8') if payload else None,
            headers=headers,
            method=method,
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f'API एरर ({endpoint}): {e}')
    return None


def fetch_market_data():
    try:
        url = PUBLIC_BASE_URL + "/v2/tickers"
        req = urllib.request.Request(url, headers={"User-Agent": "PythonBot"})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode())
            if data.get("success"):
                for ticker in data.get("result", []):
                    if ticker.get("symbol") == SYMBOL:
                        current_price = float(ticker.get("close", 0))
                        day_high = float(ticker.get("high", current_price + 200))
                        day_low = float(ticker.get("low", max(1.0, current_price - 200)))
                        return current_price, day_high, day_low
    except Exception as e:
        print(f"डेटा फेच करने में एरर: {e}")
    return None, None, None


def place_market_order(size, side):
    endpoint = "/orders"
    payload = {
        "product_id": PRODUCT_ID,
        "size": int(size / 0.001),
        "side": side,
        "order_type": "market",
    }
    print(f"-> टेस्टनेट पर आर्डर भेजा जा रहा है: {side.upper()} {size} BTC...")
    response = send_signed_request("POST", endpoint, payload)
    return response


def calculate_dynamic_qty(capital):
    extra_steps = max(0, int((capital - INITIAL_CAPITAL) / STEP_AMOUNT))
    return BASE_QTY + (extra_steps * QTY_INCREMENT)


def run_live_bot():
    global CURRENT_CAPITAL

    print("========================================")
    print(" डेल्टा एक्सचेंज क्रैश-फ्री बॉट (Sheet Log) शुरू... ")
    print("========================================")

    in_position = False
    position_side = None
    entry_price = 0.0
    highest_price_seen = 0.0
    lowest_price_seen = 0.0
    sl_price = 0.0
    tp_price = 0.0
    trade_id_counter = 1000

    current_price, day_high, day_low = fetch_market_data()
    if not current_price:
        print("एरर: मार्केट डेटा नहीं मिल पाया। 10 सेकंड बाद पुनः प्रयास...")
        time.sleep(10)
        return

    buy_trigger_level = day_high + BUFFER_POINTS
    sell_trigger_level = day_low - BUFFER_POINTS

    print(f"आज का High: {day_high:,.2f} | Buy Target: {buy_trigger_level:,.2f}")
    print(f"आज का Low: {day_low:,.2f} | Sell Target: {sell_trigger_level:,.2f}")

    last_checked_day = datetime.now().date()

    while True:
        try:
            current_time = datetime.now()

            if current_time.date() != last_checked_day:
                _, new_high, new_low = fetch_market_data()
                if new_high and new_low:
                    buy_trigger_level = new_high + BUFFER_POINTS
                    sell_trigger_level = new_low - BUFFER_POINTS
                    print("\n[NEW DAY] नए लेवल्स अपडेट हुए:")
                    print(f"Buy Target: {buy_trigger_level:,.2f}")
                    print(f"Sell Target: {sell_trigger_level:,.2f}")
                last_checked_day = current_time.date()

            current_price, day_high, day_low = fetch_market_data()
            if not current_price:
                print("⚠️ डेटा प्राप्त नहीं हुआ, 10 सेकंड बाद पुनः कोशिश...")
                time.sleep(10)
                continue

            current_qty = calculate_dynamic_qty(CURRENT_CAPITAL)
            print(
                f"[{current_time.strftime('%H:%M:%S')}] प्राइस: {current_price:,.2f}"
                f" | Buy: {buy_trigger_level:,.2f} | Sell: {sell_trigger_level:,.2f}"
            )

            if not in_position:
                if current_price >= buy_trigger_level:
                    trade_id_counter += 1
                    entry_price = current_price
                    position_side = "buy"
                    sl_price = entry_price - INITIAL_SL_POINTS
                    tp_price = entry_price + FIXED_TP_POINTS
                    highest_price_seen = entry_price
                    in_position = True

                    print(f"\n-> [HIGH BREAKOUT] Long Entry! Price: {entry_price:,.2f}")
                    place_market_order(current_qty, "buy")

                    trade_payload = {
                        "trade_id": f"TRD-{trade_id_counter}",
                        "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "symbol": SYMBOL,
                        "action": "BUY",
                        "quantity": current_qty,
                        "entry_price": entry_price,
                        "capital": CURRENT_CAPITAL,
                        "status": "OPEN"
                    }
                    log_trade_to_sheet(trade_payload)

                elif current_price <= sell_trigger_level:
                    trade_id_counter += 1
                    entry_price = current_price
                    position_side = "sell"
                    sl_price = entry_price + INITIAL_SL_POINTS
                    tp_price = entry_price - FIXED_TP_POINTS
                    lowest_price_seen = entry_price
                    in_position = True

                    print(f"\n-> [LOW BREAKDOWN] Short Entry! Price: {entry_price:,.2f}")
                    place_market_order(current_qty, "sell")

                    trade_payload = {
                        "trade_id": f"TRD-{trade_id_counter}",
                        "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "symbol": SYMBOL,
                        "action": "SELL",
                        "quantity": current_qty,
                        "entry_price": entry_price,
                        "capital": CURRENT_CAPITAL,
                        "status": "OPEN"
                    }
                    log_trade_to_sheet(trade_payload)

            elif in_position:
                if position_side == "buy":
                    if current_price > highest_price_seen:
                        highest_price_seen = current_price

                    if current_price >= tp_price:
                        pnl = current_qty * (tp_price - entry_price)
                        CURRENT_CAPITAL += pnl
                        return_pct = (pnl / (entry_price * current_qty)) * 100
                        print(f"\n-> [TP HIT] Long Profit: +{pnl:,.2f}")
                        place_market_order(current_qty, "sell")

                        trade_payload = {
                            "trade_id": f"TRD-{trade_id_counter}",
                            "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "symbol": SYMBOL,
                            "action": "BUY",
                            "quantity": current_qty,
                        "entry_price": entry_price,
                            "exit_price": tp_price,
                            "pnl": round(pnl, 2),
                            "return_pct": round(return_pct, 2),
                            "capital": round(CURRENT_CAPITAL, 2),
                            "status": "CLOSED"
                        }
                        log_trade_to_sheet(trade_payload)
                        in_position = False
                        continue

                    if highest_price_seen >= (entry_price + TRAILING_TRIGGER):
                        new_sl = highest_price_seen - TRAILING_DISTANCE
                        if new_sl > sl_price:
                            sl_price = new_sl
                            print(f"-> [TSL UPDATE] New SL: {sl_price:,.2f}")

                    if current_price <= sl_price:
                        pnl = current_qty * (sl_price - entry_price)
                        CURRENT_CAPITAL += pnl
                        return_pct = (pnl / (entry_price * current_qty)) * 100
                        print(f"\n-> [SL HIT] Long Loss: {pnl:,.2f}")
                        place_market_order(current_qty, "sell")

                        trade_payload = {
                            "trade_id": f"TRD-{trade_id_counter}",
                            "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "symbol": SYMBOL,
                            "action": "BUY",
                            "quantity": current_qty,
                            "entry_price": entry_price,
                            "exit_price": sl_price,
                            "pnl": round(pnl, 2),
                            "return_pct": round(return_pct, 2),
                            "capital": round(CURRENT_CAPITAL, 2),
                            "status": "CLOSED"
                        }
                        log_trade_to_sheet(trade_payload)
                        in_position = False

                elif position_side == "sell":
                    if current_price < lowest_price_seen:
                        lowest_price_seen = current_price

                    if current_price <= tp_price:
                        pnl = current_qty * (entry_price - tp_price)
                        CURRENT_CAPITAL += pnl
                        return_pct = (pnl / (entry_price * current_qty)) * 100
                        print(f"\n-> [TP HIT] Short Profit: +{pnl:,.2f}")
                        place_market_order(current_qty, "buy")

                        trade_payload = {
                            "trade_id": f"TRD-{trade_id_counter}",
                            "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "symbol": SYMBOL,
                            "action": "SELL",
                            "quantity": current_qty,
                            "entry_price": entry_price,
                            "exit_price": tp_price,
                            "pnl": round(pnl, 2),
                            "return_pct": round(return_pct, 2),
                            "capital": round(CURRENT_CAPITAL, 2),
                            "status": "CLOSED"
                        }
                        log_trade_to_sheet(trade_payload)
                        in_position = False
                        continue

                    if lowest_price_seen <= (entry_price - TRAILING_TRIGGER):
                        new_sl = lowest_price_seen + TRAILING_DISTANCE
                        if new_sl < sl_price:
                            sl_price = new_sl
                            print(f"-> [TSL UPDATE] New Short SL: {sl_price:,.2f}")

                    if current_price >= sl_price:
                        pnl = current_qty * (entry_price - sl_price)
                        CURRENT_CAPITAL += pnl
                        return_pct = (pnl / (entry_price * current_qty)) * 100
                        print(f"\n-> [SL HIT] Short Loss: {pnl:,.2f}")
                        place_market_order(current_qty, "buy")

                        trade_payload = {
                            "trade_id": f"TRD-{trade_id_counter}",
                            "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "symbol": SYMBOL,
                            "action": "SELL",
                            "quantity": current_qty,
                            "entry_price": entry_price,
                            "exit_price": sl_price,
                            "pnl": round(pnl, 2),
                            "return_pct": round(return_pct, 2),
                            "capital": round(CURRENT_CAPITAL, 2),
                            "status": "CLOSED"
                        }
                        log_trade_to_sheet(trade_payload)
                        in_position = False

            time.sleep(30)

        except Exception as loop_err:
            print(f"⚠️ लूप में एरर आई (बॉट फिर से चालू हो रहा है): {loop_err}")
            time.sleep(10)


if __name__ == "__main__":
    while True:
        try:
            run_live_bot()
        except Exception as main_err:
            print(f"⚠️ क्रिटिकल एरर, बॉट रीस्टार्ट हो रहा है: {main_err}")
            time.sleep(10)
