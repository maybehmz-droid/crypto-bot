import requests
import time
import json
from datetime import datetime

TELEGRAM_TOKEN = "8638178539:AAERhogjntcBbd1_XI2ch5siQcoWHH4aZek"
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
CHECK_INTERVAL = 900  # 15 minutes

def send_telegram(chat_id, message):
    url = f"{TELEGRAM_URL}/sendMessage"
    data = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    requests.post(url, json=data)

def get_updates(offset=None):
    url = f"{TELEGRAM_URL}/getUpdates"
    params = {"timeout": 30, "offset": offset}
    r = requests.get(url, params=params, timeout=35)
    return r.json()

def get_okx_data(symbol):
    try:
        # Get ticker
        ticker_url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol}"
        ticker = requests.get(ticker_url, timeout=10).json()
        
        if ticker["code"] != "0":
            return None
            
        data = ticker["data"][0]
        price = float(data["last"])
        vol_24h = float(data["vol24h"])
        change_24h = float(data["sodUtc8"]) if data["sodUtc8"] else 0
        price_open = float(data["open24h"])
        change_pct = ((price - price_open) / price_open) * 100
        
        # Get candles for volatility analysis
        candles_url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar=1H&limit=24"
        candles = requests.get(candles_url, timeout=10).json()
        
        if candles["code"] != "0":
            return None
        
        closes = [float(c[4]) for c in candles["data"]]
        highs = [float(c[2]) for c in candles["data"]]
        lows = [float(c[3]) for c in candles["data"]]
        volumes = [float(c[5]) for c in candles["data"]]
        
        # Average volume
        avg_vol = sum(volumes) / len(volumes) if volumes else 0
        current_vol = volumes[0] if volumes else 0
        vol_ratio = (current_vol / avg_vol) if avg_vol > 0 else 1
        
        # Historical 5% moves (last 24 hours candles)
        five_pct_moves = 0
        for i in range(len(highs)):
            if lows[i] > 0:
                candle_move = ((highs[i] - lows[i]) / lows[i]) * 100
                if candle_move >= 5:
                    five_pct_moves += 1
        
        hist_probability = (five_pct_moves / len(highs)) * 100 if highs else 0
        
        return {
            "symbol": symbol,
            "price": price,
            "change_pct": change_pct,
            "vol_ratio": vol_ratio,
            "hist_probability": hist_probability,
            "closes": closes
        }
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

def get_hyperliquid_whales(symbol):
    try:
        coin = symbol.replace("-USDT", "")
        url = "https://api.hyperliquid.xyz/info"
        payload = {"type": "recentTrades", "coin": coin}
        r = requests.post(url, json=payload, timeout=10)
        trades = r.json()
        
        if not isinstance(trades, list):
            return {"buy_vol": 0, "sell_vol": 0, "whale_detected": False}
        
        buy_vol = 0
        sell_vol = 0
        whale_threshold = 100000  # $100k+
        whale_detected = False
        
        for trade in trades[:50]:
            size = float(trade.get("sz", 0))
            price = float(trade.get("px", 0))
            value = size * price
            side = trade.get("side", "")
            
            if value >= whale_threshold:
                whale_detected = True
            
            if side == "B":
                buy_vol += value
            else:
                sell_vol += value
        
        return {
            "buy_vol": buy_vol,
            "sell_vol": sell_vol,
            "whale_detected": whale_detected
        }
    except Exception as e:
        print(f"Hyperliquid error: {e}")
        return {"buy_vol": 0, "sell_vol": 0, "whale_detected": False}

def calculate_signal(okx_data, whale_data):
    score = 0
    direction = "NEUTRAL"
    
    change = okx_data["change_pct"]
    vol_ratio = okx_data["vol_ratio"]
    hist_prob = okx_data["hist_probability"]
    buy_vol = whale_data["buy_vol"]
    sell_vol = whale_data["sell_vol"]
    whale_detected = whale_data["whale_detected"]
    
    # Volume analysis
    if vol_ratio > 1.5:
        score += 20
    elif vol_ratio > 1.2:
        score += 10
    
    # Price momentum
    if abs(change) > 3:
        score += 25
        direction = "LONG" if change > 0 else "SHORT"
    elif abs(change) > 1.5:
        score += 15
        direction = "LONG" if change > 0 else "SHORT"
    
    # Historical probability
    if hist_prob > 30:
        score += 20
    elif hist_prob > 15:
        score += 10
    
    # Whale activity
    if whale_detected:
        score += 20
    
    if buy_vol > sell_vol * 1.5:
        score += 15
        if direction == "NEUTRAL":
            direction = "LONG"
    elif sell_vol > buy_vol * 1.5:
        score += 15
        if direction == "NEUTRAL":
            direction = "SHORT"
    
    return min(score, 95), direction

def format_signal(okx_data, whale_data, score, direction):
    symbol = okx_data["symbol"].replace("-", "/")
    price = okx_data["price"]
    change = okx_data["change_pct"]
    vol_ratio = okx_data["vol_ratio"]
    hist_prob = okx_data["hist_probability"]
    buy_vol = whale_data["buy_vol"]
    sell_vol = whale_data["sell_vol"]
    whale_detected = whale_data["whale_detected"]
    
    direction_emoji = "📈" if direction == "LONG" else "📉" if direction == "SHORT" else "➡️"
    whale_text = "✅ تم رصد صفقات كبيرة" if whale_detected else "❌ لا يوجد نشاط ملحوظ"
    
    buy_vol_fmt = f"${buy_vol/1000:.1f}K" if buy_vol < 1000000 else f"${buy_vol/1000000:.2f}M"
    sell_vol_fmt = f"${sell_vol/1000:.1f}K" if sell_vol < 1000000 else f"${sell_vol/1000000:.2f}M"
    
    msg = f"""🚨 <b>إشارة تداول - {symbol}</b>

{direction_emoji} <b>الاتجاه:</b> {direction}
💰 <b>السعر الحالي:</b> ${price:,.2f}
📊 <b>التغير 24 ساعة:</b> {change:+.2f}%
🎯 <b>احتمالية حركة 5%+:</b> {score}%

🐋 <b>نشاط الحيتان (Hyperliquid):</b>
{whale_text}
• حجم الشراء: {buy_vol_fmt}
• حجم البيع: {sell_vol_fmt}

📈 <b>بيانات إضافية:</b>
• الحجم مقارنة بالمعتاد: {vol_ratio:.1f}x
• تكرار حركة 5%+ تاريخياً: {hist_prob:.0f}%

⚠️ <b>تأكد بالتحليل الفني:</b>
EMA + RSI + دعوم/مقاومات + فيبوناتشي
<b>لا تنسى Stop Loss دايماً!</b>

🕐 {datetime.now().strftime('%H:%M - %d/%m/%Y')}"""
    
    return msg

def run_bot():
    print("Bot started!")
    chat_ids = set()
    last_offset = None
    last_check = {}
    
    for symbol in SYMBOLS:
        last_check[symbol] = 0
    
    while True:
        try:
            # Get new messages
            updates = get_updates(last_offset)
            
            if updates.get("ok") and updates.get("result"):
                for update in updates["result"]:
                    last_offset = update["update_id"] + 1
                    
                    if "message" in update:
                        chat_id = update["message"]["chat"]["id"]
                        text = update["message"].get("text", "")
                        
                        if text == "/start":
                            chat_ids.add(chat_id)
                            send_telegram(chat_id, 
                                "🤖 <b>أهلاً! البوت شغال دلوقتي</b>\n\n"
                                "هراقبلك BTC و ETH و SOL و BNB و DOGE و AVAX
وهبعتلك إشارات لما يلاقي فرصة قوية 🚀\n\n"
                                "الأوامر:\n"
                                "/check - فحص فوري\n"
                                "/stop - إيقاف الإشارات")
                        
                        elif text == "/check":
                            chat_ids.add(chat_id)
                            send_telegram(chat_id, "⏳ بفحص السوق دلوقتي...")
                            
                            for symbol in SYMBOLS:
                                okx_data = get_okx_data(symbol)
                                if okx_data:
                                    whale_data = get_hyperliquid_whales(symbol)
                                    score, direction = calculate_signal(okx_data, whale_data)
                                    msg = format_signal(okx_data, whale_data, score, direction)
                                    send_telegram(chat_id, msg)
                                    time.sleep(1)
                        
                        elif text == "/stop":
                            chat_ids.discard(chat_id)
                            send_telegram(chat_id, "✅ تم إيقاف الإشارات")
            
            # Auto check every 15 minutes
            current_time = time.time()
            for symbol in SYMBOLS:
                if current_time - last_check[symbol] >= CHECK_INTERVAL:
                    last_check[symbol] = current_time
                    
                    okx_data = get_okx_data(symbol)
                    if okx_data:
                        whale_data = get_hyperliquid_whales(symbol)
                        score, direction = calculate_signal(okx_data, whale_data)
                        
                        # Only send if score is significant
                        if score >= 50 and chat_ids:
                            msg = format_signal(okx_data, whale_data, score, direction)
                            for chat_id in chat_ids:
                                send_telegram(chat_id, msg)
                    
                    time.sleep(2)
            
            time.sleep(3)
            
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_bot()
