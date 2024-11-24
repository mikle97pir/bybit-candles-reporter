from pybit.unified_trading import HTTP
from datetime import datetime, timezone, timedelta
from tqdm import tqdm
import mplfinance as mpf
import pandas as pd 
from telegram import Bot
import asyncio
from dotenv import load_dotenv
import os

def plot_candles(candles, symbol, pos=None, savefig=None):

    df = pd.DataFrame(candles).astype(
        {
            'Date': 'datetime64[s, UTC]',
            'Open': 'float64',
            'High': 'float64',
            'Low': 'float64',
            'Close': 'float64',
            'Volume': 'float64'
        }
    ).set_index('Date')

    alines = None
    if pos is not None:
        ymin = candles[pos]['Open']
        ymax = candles[pos]['Close']
        ts = candles[pos]['Date']
        alines = [[(ts, ymin), (ts, ymax)]]

    if savefig is not None:
        mpf.plot(
            df,
            type='candle',
            style='charles',
            title=symbol,
            ylabel='Price',
            volume=True,
            ylabel_lower='Volume',
            figratio=(20, 9),
            figscale=1.5,
            alines=alines,
            savefig=savefig
        )
    else:
        mpf.plot(
            df,
            type='candle',
            style='charles',
            title=symbol,
            ylabel='Price',
            volume=True,
            ylabel_lower='Volume',
            figratio=(20, 9),
            figscale=1.5,
            alines=alines,
        )

def plot_pattern(pattern, candles, win_len, savefig=None):
    symbol = pattern['symbol']
    i = pattern['i']
    j = pattern['j']
    left = i
    right = min(j + win_len, len(candles[symbol]))
    plot_candles(candles[symbol][left:right], symbol, j-left, savefig)

async def main():

    load_dotenv()
    bot_token = os.getenv('BOT_TOKEN')
    chat_id = os.getenv('CHAT_ID')

    session = HTTP()

    instruments = session.get_instruments_info(category='spot', base_coin='BTC')['result']['list']
    instruments = [inst for inst in instruments if inst['quoteCoin'] == 'USDT']

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=10)

    start_timestamp_ms = int(1000 * start_time.timestamp())
    end_timestamp_ms = int(1000 * end_time.timestamp())

    raw_candles = {}
    for inst in tqdm(instruments):
        symbol = inst['symbol']
        raw_candles[symbol] = session.get_kline(
            category='spot',
            symbol=symbol,
            interval=30,
            start=start_timestamp_ms,
            end=end_timestamp_ms,
            limit=1000
        )['result']['list']

    candles = {}
    for sym, ls in raw_candles.items():
        reverse_ls = []
        for candle in ls:
            reverse_ls.insert(0, {
                'Date': datetime.fromtimestamp(int(candle[0])//1000, timezone.utc),
                'Open': float(candle[1]),
                'High': float(candle[2]),
                'Low': float(candle[3]),
                'Close': float(candle[4]),
                'Volume': float(candle[5])
            })
        candles[sym] = reverse_ls

    patterns = []
    win_len = 24 * 2
    for sym, ls in candles.items():
        for i in range(0, len(ls) - win_len + 1):
            j = i + win_len - 1
            last_delta = ls[j]['Close'] - ls[j]['Open']
            if last_delta > 0:
                max_abs_delta = max(abs(candle['Close'] - candle['Open']) for candle in ls[i:j])
                if abs(last_delta) > max_abs_delta:
                    price_change = ls[j]['Close'] / ls[j]['Open']
                    last_delta_strength = abs(last_delta) / max_abs_delta if max_abs_delta > 0 else float('inf')
                    patterns.append(
                        {
                            'symbol': sym,
                            'i': i,
                            'j': j,
                            'j_open': ls[j]['Open'],
                            'j_close': ls[j]['Close'],
                            'price_change': price_change,
                            'last_delta': last_delta,
                            'max_abs_delta': max_abs_delta,
                            'last_delta_strength': last_delta_strength
                        }
                    )

    patterns = sorted(patterns, key=lambda p: p['last_delta_strength'], reverse=True)
    # good_patterns = [p for p in patterns if p['price_change'] > 1.2 and p['last_delta_strength'] > 5 and p['last_delta_strength'] < 50] 

    bot = Bot(token=bot_token)

    send_time_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M') 
    i = 0
    for pattern in patterns:
        if pattern['j'] == len(candles[pattern['symbol']]) - 1:
            plot_pattern(pattern, candles, win_len, savefig='candles.png')
            with open('candles.png', 'rb') as chart:
                await bot.send_photo(
                    chat_id=chat_id, 
                    photo=chart, 
                    caption=f"*{send_time_str}*\n*{i}: {pattern['symbol']}*\n`price_change = {pattern['price_change']:.2f}\nlast_delta_strength = {pattern['last_delta_strength']:.2f}`",
                    parse_mode='Markdown'
                )
            i += 1

if __name__ == "__main__": 
    asyncio.run(main())