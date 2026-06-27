import os
import time
import logging
import pandas as pd
import sys
from dotenv import load_dotenv

load_dotenv()

# ===================== 配置日志 =====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


TELEGRAM_BOT_TOKEN = os.getenv('BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID', '')

def send_telegram(message, screenshot_path=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    tz_offset = timezone(timedelta(hours=8))
    time_str = datetime.now(tz_offset).strftime("%Y-%m-%d %H:%M:%S") + " HKT"
    full_message = f"🎉 测速 \n\n：{time_str}\n\n{message}"
    try:
        if screenshot_path and os.path.exists(screenshot_path):
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            with open(screenshot_path, 'rb') as photo:
                requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "caption": full_message}, files={'photo': photo}, timeout=20)
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": full_message}, timeout=10)
        logger.info("✅ Telegram 通知发送成功")
    except Exception as e:
        logger.warning(f"⚠️ Telegram 发送失败: {e}")

def csv_to_txt(csv_filename, output_filename, area_name):
    df = pd.read_csv(csv_filename, encoding='utf-8')
    ips = df.iloc[:, 0]
    download_speeds = df.iloc[:, 5]
    resulttext=""
    with open(output_filename, 'w', encoding='utf-8') as f:
        for i, (ip, speed) in enumerate(zip(ips, download_speeds)):
            resulttext+=f"{ip}#{area_name} {i+1} ↓ {speed}MB/s\n"
            f.write(f"{ip}#{area_name} {i+1} ↓ {speed}MB/s\n")
    return resulttext



speedtext = csv_to_txt("HKG.csv", "HKG.txt", "中国香港")
speedtext+=csv_to_txt("KHH.csv", "KHH.txt", "中国台湾")
speedtext+=csv_to_txt("NRT.csv", "NRT.txt", "日本东京")
speedtext+=csv_to_txt("LAX.csv", "LAX.txt", "美国洛杉矶")
speedtext+=csv_to_txt("SEA.csv", "SEA.txt", "美国西雅图")
speedtext+=csv_to_txt("SJC.csv", "SJC.txt", "美国圣何塞")
speedtext+=csv_to_txt("FRA.csv", "FRA.txt", "德国法兰克福")

send_telegram(speedtext)
