import requests
import json
import sys
import time
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import threading
import numpy as np
from matplotlib.widgets import Slider
import matplotlib.animation as animation
import telegram
import asyncio
import csv
import httpx

# Telegram Bot credentials
telegram_token = 'your_token'
chat_id = 'your_id'

try:
    bot = telegram.Bot(token=telegram_token)
    print("Telegram bot initialized successfully.")
except Exception as e:
    print(f"Failed to initialize Telegram bot: {e}", file=sys.stderr)
    sys.exit(1)

async def send_telegram_message(message):
    try:
        await bot.send_message(chat_id=chat_id, text=message)
        print(f"Sent message: {message}")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}", file=sys.stderr)

fig, ax_kline = plt.subplots()

# Display today's date with a message when the program starts
print(datetime.now().strftime('%Y-%m-%d') + ' 賺錢囉')

# Send Telegram message when the program starts
loop = asyncio.get_event_loop()
loop.run_until_complete(send_telegram_message('2024-10-04 賺錢囉'))
plt.subplots_adjust(bottom=0.25)

slider_ax = plt.axes([0.1, 0.1, 0.8, 0.03], facecolor='lightgoldenrodyellow')

buy_points = []
sell_points = []
close_points = []
current_position = None  # Track current position ('buy' or 'sell')
current_message = None
current_ma_message = None

def get_binance_klines(symbol: str, interval: str, limit: int):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    retry_count = 0
    max_retries = 5

    while retry_count < max_retries:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            retry_count += 1
            print(f"Request failed: {e}. Retrying {retry_count}/{max_retries}...")
            time.sleep(10 * retry_count)
            continue

        return response.json()
    print("Failed to fetch data after maximum retries.")
    return None

def calculate_moving_average(data, window):
    return np.convolve(data, np.ones(window)/window, mode='valid')

def calculate_rsi(data, window):
    deltas = np.diff(data)
    seed = deltas[:window]
    up = seed[seed >= 0].sum() / window
    down = -seed[seed < 0].sum() / window
    rs = up / down
    rsi = np.zeros_like(data)
    rsi[:window] = 100. - 100. / (1. + rs)

    for i in range(window, len(data)):
        delta = deltas[i - 1]  # because the diff is 1 shorter
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta

        up = (up * (window - 1) + upval) / window
        down = (down * (window - 1) + downval) / window

        rs = up / down
        rsi[i] = 100. - 100. / (1. + rs)

    return rsi

def plot_kline(data, start_index):
    if start_index + 15 > len(data):
        start_index = len(data) - 15
    ax_kline.clear()
    end_index = start_index + 15
    data = data[start_index:end_index]

    dates = [datetime.fromtimestamp(item[0] / 1000) for item in data]
    opens = [float(item[1]) for item in data]
    highs = [float(item[2]) for item in data]
    lows = [float(item[3]) for item in data]
    closes = [float(item[4]) for item in data]

    ax_kline.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    ax_kline.xaxis.set_major_locator(mdates.HourLocator(interval=1))

    for i in range(len(dates)):
        color = 'green' if closes[i] >= opens[i] else 'red'
        ax_kline.plot([dates[i], dates[i]], [lows[i], highs[i]], color=color)
        ax_kline.plot([dates[i], dates[i]], [opens[i], closes[i]], color=color, linewidth=6)
        ax_kline.text(dates[i], closes[i], f'{closes[i]:.2f}', fontsize=8, ha='center', va='bottom', color=color)

    # Plot buy, sell, and close points
    for point in buy_points:
        ax_kline.plot(point['time'], point['price'], marker='^', color='green', markersize=10, label='Buy')
    for point in sell_points:
        ax_kline.plot(point['time'], point['price'], marker='v', color='red', markersize=10, label='Sell')
    for point in close_points:
        ax_kline.plot(point['time'], point['price'], marker='o', color='blue', markersize=6, label='Close')

    ax_kline.set_xlabel('Time')
    ax_kline.set_ylabel('Price')
    ax_kline.set_title('Bitcoin 1-Hour K-Line Chart (15 K-Bars View)')
    plt.xticks(rotation=45)
    plt.tight_layout()
    ax_kline.legend()

def update_chart(frame):
    global data, current_position,current_message,current_ma_message
    data = get_binance_klines("BTCUSDT", "1h", 1440)
    if data:
        latest_kline = data[-1]
        latest_close = float(latest_kline[4])
        latest_time = datetime.fromtimestamp(latest_kline[0] / 1000)
        print(f"Latest K-Line Time: {latest_time}, Close Price: {latest_close}")
    if data:
        plot_kline(data, len(data) - 15)
        plt.draw()
        closes = [float(item[4]) for item in data]
        ma_30 = calculate_moving_average(closes, 30)[-1] if len(closes) >= 30 else None
        ma_60 = calculate_moving_average(closes, 60)[-1] if len(closes) >= 60 else None
        ma_120 = calculate_moving_average(closes, 120)[-1] if len(closes) >= 120 else None
        rsi_14 = calculate_rsi(closes, 14)[-1] if len(closes) > 14 else None

        print(f"MA 30: {ma_30}, MA 60: {ma_60}, MA 120: {ma_120}, RSI 14: {rsi_14}")

        # Check for entry signals
        if ma_30 and ma_60 and ma_120 and rsi_14:
            if ma_30 < ma_60 < ma_120 and rsi_14 < 30:
                message = f"空下去就對了 {latest_time}, Close Price: {latest_close}"
                asyncio.run_coroutine_threadsafe(send_telegram_message(message), loop)
                print(message)
                
            elif ma_30 > ma_60 > ma_120 and rsi_14 > 70:
                message = f"快點買爆 {latest_time}, Close Price: {latest_close}"
                asyncio.run_coroutine_threadsafe(send_telegram_message(message), loop)
                print(message)
                

        # Check for RSI alerts
        if rsi_14 >= 70 and (current_message != 'rsi_alert_70'):
            message = f"RSI 超過 70 囉: {rsi_14}"
            asyncio.run_coroutine_threadsafe(send_telegram_message(message), loop)
            print(message)
            current_message = 'rsi_alert_70'
        elif rsi_14 <= 30 and (current_message != 'rsi_alert_30'):
            message = f"RSI 跌破 30 囉: {rsi_14}"
            asyncio.run_coroutine_threadsafe(send_telegram_message(message), loop)
            print(message)
            current_message = 'rsi_alert_30'
        elif rsi_14 <=70 and rsi_14 >=30 and (current_message != 'rsi_alert_70_30'):
            message = f"RSI又到那該死的區間了: {rsi_14}"
            asyncio.run_coroutine_threadsafe(send_telegram_message(message), loop)
            print(message)
            current_message = 'rsi_alert_70_30'

        if ma_30 and ma_60 and ma_120:
            if ma_30 < ma_60 < ma_120 and (current_ma_message != 'ALLPUT'):
                message = f"我靠!大家都在空 {latest_time}, Close Price: {latest_close}"
                asyncio.run_coroutine_threadsafe(send_telegram_message(message), loop)
                current_ma_message = 'ALLPUT'
                print(message)
            elif ma_30 > ma_60 > ma_120 and (current_ma_message != 'ALLBUY'):
                message = f"我靠!大家狂買ㄟ {latest_time}, Close Price: {latest_close}"
                asyncio.run_coroutine_threadsafe(send_telegram_message(message), loop)
                current_ma_message = 'ALLBUY'
                print(message)
            else:
                if (current_ma_message != 'WTF'):
                    message = f"多空拔河中! {latest_time}, Close Price: {latest_close}"
                    asyncio.run_coroutine_threadsafe(send_telegram_message(message), loop)
                    current_ma_message = 'WTF'
                    print(message)

        # Check for exit signals (平倉)
        if current_position == 'buy' and ma_120 > ma_60 > ma_30:
            message = f"快點給我平倉（多單） {latest_time}, Close Price: {latest_close}"
            asyncio.run_coroutine_threadsafe(send_telegram_message(message), loop)
            print(message)
        elif current_position == 'sell' and ma_30 > ma_60 > ma_120:
            message = f"快點給我平倉（空單） {latest_time}, Close Price: {latest_close}"
            asyncio.run_coroutine_threadsafe(send_telegram_message(message), loop)
            print(message)

# Load all data initially
data = get_binance_klines("BTCUSDT", "1h", 1440)
if data:
    plot_kline(data, len(data) - 15)
    plt.draw()

kline_slider = Slider(slider_ax, 'K-Line Index', 0, max(0, len(data) - 15), valinit=max(0, len(data) - 15), valstep=1)
kline_slider.on_changed(lambda val: plot_kline(data, int(val)))

ani = animation.FuncAnimation(fig, update_chart, interval=5000, cache_frame_data=False)


# Thread to listen to user input for buy/sell commands
def user_input_listener():
    global buy_points, sell_points, close_points, current_position
    while True:
        user_input = input("Enter command (buy/sell/close): ").strip().lower()
        if user_input == 'buy':
            if data:
                latest_kline = data[-1]
                buy_point = {'time': datetime.fromtimestamp(latest_kline[0] / 1000), 'price': float(latest_kline[2])}  # Use high price for buy marker
                buy_points.append(buy_point)
                print(f"Buy order placed at {buy_point['time']} for price {buy_point['price']}")
                with open('trade_records.csv', mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(['Buy', buy_point['time'], buy_point['price']])
                current_position = 'buy'
                asyncio.run_coroutine_threadsafe(send_telegram_message(f"Buy order placed at {buy_point['time']} for price {buy_point['price']}"), loop)
        elif user_input == 'sell':
            if data:
                latest_kline = data[-1]
                sell_point = {'time': datetime.fromtimestamp(latest_kline[0] / 1000), 'price': float(latest_kline[3])}  # Use low price for sell marker
                sell_points.append(sell_point)
                print(f"Sell order placed at {sell_point['time']} for price {sell_point['price']}")
                with open('trade_records.csv', mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(['Sell', sell_point['time'], sell_point['price']])
                current_position = 'sell'
                asyncio.run_coroutine_threadsafe(send_telegram_message(f"Sell order placed at {sell_point['time']} for price {sell_point['price']}"), loop)
        elif user_input == 'close':
            if data and current_position is not None:
                latest_kline = data[-1]
                close_point = {'time': datetime.fromtimestamp(latest_kline[0] / 1000), 'price': float(latest_kline[4])}  # Use close price for close marker
                close_points.append(close_point)
                print(f"Close order placed at {close_point['time']} for price {close_point['price']}")
                with open('trade_records.csv', mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(['Close', close_point['time'], close_point['price']])
                asyncio.run_coroutine_threadsafe(send_telegram_message(f"Close order placed at {close_point['time']} for price {close_point['price']}"), loop)
                current_position = None
        elif user_input == 'hello':
                # Reply with current MA and RSI values
                if data:
                    closes = [float(item[4]) for item in data]
                    ma_30 = calculate_moving_average(closes, 30)[-1] if len(closes) >= 30 else None
                    ma_60 = calculate_moving_average(closes, 60)[-1] if len(closes) >= 60 else None
                    ma_90 = calculate_moving_average(closes, 90)[-1] if len(closes) >= 90 else None
                    rsi_14 = calculate_rsi(closes, 14)[-1] if len(closes) > 14 else None

                    message = (
                        f"嘿!我還活著喔。\n"
                        f"MA30: {ma_30}\n"
                        f"MA60: {ma_60}\n"
                        f"MA90: {ma_90}\n"
                        f"RSI14: {rsi_14}"
                    )
                else:
                    message = "目前無法取得 K 線資料。"
                asyncio.run_coroutine_threadsafe(send_telegram_message(message), loop)
        else:
            print("Invalid command. Please enter 'buy', 'sell', or 'close'.")

input_thread = threading.Thread(target=user_input_listener, daemon=True)
input_thread.start()

# Thread to listen to Telegram messages for buy/sell/close commands
async def telegram_listener():
    global buy_points, sell_points, close_points, current_position
    offset = None
    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=10)
        except (telegram.error.TimedOut, asyncio.TimeoutError, httpx.ReadTimeout) as e:
            print(f"Timeout occurred while listening for Telegram messages: {e}")
            await asyncio.sleep(5)  # 等待 5 秒後重試
            continue
        except Exception as e:
            print(f"Unexpected error in telegram_listener: {e}")
            break
        for update in updates:
            if update.message:
                user_input = update.message.text.strip().lower()
                if user_input == 'buy':
                    if data:
                        latest_kline = data[-1]
                        buy_point = {'time': datetime.fromtimestamp(latest_kline[0] / 1000), 'price': float(latest_kline[2])}  # Use high price for buy marker
                        buy_points.append(buy_point)
                        print(f"Buy order placed at {buy_point['time']} for price {buy_point['price']}")
                        with open('trade_records.csv', mode='a', newline='') as file:
                            writer = csv.writer(file)
                            writer.writerow(['Buy', buy_point['time'], buy_point['price']])
                        current_position = 'buy'
                        await send_telegram_message(f"可樂 {buy_point['time']} for price {buy_point['price']}")
                elif user_input == 'sell':
                    if data:
                        latest_kline = data[-1]
                        sell_point = {'time': datetime.fromtimestamp(latest_kline[0] / 1000), 'price': float(latest_kline[3])}  # Use low price for sell marker
                        sell_points.append(sell_point)
                        print(f"Sell order placed at {sell_point['time']} for price {sell_point['price']}")
                        with open('trade_records.csv', mode='a', newline='') as file:
                            writer = csv.writer(file)
                            writer.writerow(['Sell', sell_point['time'], sell_point['price']])
                        current_position = 'sell'
                        await send_telegram_message(f"葡萄 {sell_point['time']} for price {sell_point['price']}")
                elif user_input == 'close':
                    if data and current_position is not None:
                        latest_kline = data[-1]
                        close_point = {'time': datetime.fromtimestamp(latest_kline[0] / 1000), 'price': float(latest_kline[4])}  # Use close price for close marker
                        close_points.append(close_point)
                        print(f"Close order placed at {close_point['time']} for price {close_point['price']}")
                        with open('trade_records.csv', mode='a', newline='') as file:
                            writer = csv.writer(file)
                            writer.writerow(['Close', close_point['time'], close_point['price']])
                        current_position = None
                        await send_telegram_message(f"兩手空空 {close_point['time']} for price {close_point['price']}")
                elif user_input == 'hello':
                # Reply with current MA and RSI values
                    if data:
                        closes = [float(item[4]) for item in data]
                        ma_30 = calculate_moving_average(closes, 30)[-1] if len(closes) >= 30 else None
                        ma_60 = calculate_moving_average(closes, 60)[-1] if len(closes) >= 60 else None
                        ma_120 = calculate_moving_average(closes, 120)[-1] if len(closes) >= 120 else None
                        rsi_14 = calculate_rsi(closes, 14)[-1] if len(closes) > 14 else None
                        latest_close = closes[-1]  # 最新收盤價

                        message = (
                            f"嘿!庵還活著喔\n"
                            f"目前價格: {latest_close:.2f}\n"
                            f"MA30: {ma_30:.2f}\n"
                            f"MA60: {ma_60:.2f}\n"
                            f"MA120: {ma_120:.2f}\n"
                            f"RSI14: {rsi_14:.2f}"
                        )
                    else:
                        message = "目前無法取得 K 線資料。"

                    await send_telegram_message(message)
                    print(message)

                offset = update.update_id + 1

# Start Telegram listener in a separate task within a new event loop
def start_telegram_listener():
    loop.run_until_complete(telegram_listener())

tg_thread = threading.Thread(target=start_telegram_listener, daemon=True)
tg_thread.start()

plt.show()

# Check for window close event
def handle_close(evt):
    try:
        loop.run_until_complete(send_telegram_message('Program closed by user.'))
    except Exception as e:
        print(f"Failed to send Telegram message on window close: {e}", file=sys.stderr)

fig.canvas.mpl_connect('close_event', handle_close)

# Send Telegram message when the program ends normally
def on_exit():
    try:
        loop.run_until_complete(send_telegram_message('Program ended successfully.'))
    except Exception as e:
        print(f"Failed to send Telegram message on exit: {e}", file=sys.stderr)

import atexit
atexit.register(on_exit)

# Keep the main thread alive
try:
    while True:
        time.sleep(1)
except Exception as e:
    try:
        loop.run_until_complete(send_telegram_message(f'Program crashed with error: {str(e)}'))
    except Exception as e_send:
        print(f"Failed to send Telegram message on crash: {e_send}", file=sys.stderr)
except Exception as e:
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(send_telegram_message(f'Program crashed with error: {str(e)}'))
    except Exception as e_send:
        print(f"Failed to send Telegram message on crash: {e_send}", file=sys.stderr)
    print(f'Error: {str(e)}', file=sys.stderr)
    sys.exit(1)