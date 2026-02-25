import asyncio
import json
import logging
import re
import os
import subprocess
from datetime import datetime
from pathlib import Path
from telegram.ext import Application
from playwright.async_api import async_playwright

# ==========================================
# 1. قسم الإعدادات
# ==========================================
BOT_TOKEN = "8204515967:AAG6VnSCJ3_-K-XxMRKK2ClB83aW7WZ2dhc"
CHANNEL_ID = -1003678896538

IVASMS_EMAIL = "vipbyr1@gmail.com"
IVASMS_PASSWORD = "svena11.m"

LOGIN_URL = "https://www.ivasms.com/login"
SMS_URL = "https://www.ivasms.com/portal/sms/received/getsms"

CHECK_INTERVAL = 15
STATE_FILE = "sent_sms.json"

# تعديل المسار ليكون متوافقاً مع بيئة الاستضافة
BROWSER_PATH = os.path.join(os.getcwd(), "pw-browsers")
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = BROWSER_PATH

# ==========================================
# 2. إعدادات البيئة وتثبيت المتصفح
# ==========================================
def install_playwright():
    try:
        logging.info("⏳ التأكد من تثبيت المتصفح والاعتماديات...")
        # تثبيت المتصفح
        subprocess.run(["python3", "-m", "playwright", "install", "chromium"], check=True)
        # تثبيت مكتبات النظام الضرورية (هام جداً لـ Railway)
        subprocess.run(["python3", "-m", "playwright", "install-deps"], check=True)
        logging.info("✅ تم التجهيز بنجاح!")
    except Exception as e:
        logging.error(f"❌ خطأ أثناء التثبيت: {e}")

# ==========================================
# 3. الوظائف المساعدة
# ==========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def load_sent():
    try:
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_sent(data):
    with open(STATE_FILE, "w") as f:
        json.dump(list(data), f)

def extract_code(text):
    m = re.search(r"\b\d{4,8}\b", text)
    return m.group() if m else "N/A"

# ==========================================
# 4. جلب الرسائل (المتصفح المعدل)
# ==========================================
async def fetch_sms():
    async with async_playwright() as p:
        try:
            # إضافة الـ Arguments لمنع الانهيار
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--no-first-run",
                    "--no-zygote",
                    "--single-process" # مفيد في السيرفرات ذات الموارد المحدودة
                ]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            await page.goto(LOGIN_URL, timeout=60000)
            await page.fill('input[name="email"]', IVASMS_EMAIL)
            await page.fill('input[name="password"]', IVASMS_PASSWORD)
            await page.click('button[type="submit"]')

            await page.wait_for_selector("text=Logout", timeout=30000)
            logging.info("✅ تم تسجيل الدخول بنجاح")

            await page.goto(SMS_URL, timeout=60000)
            await page.wait_for_selector("div.card-body p", timeout=30000)

            elements = await page.query_selector_all("div.card-body p")
            messages = []
            for el in elements:
                text = await el.inner_text()
                if not text.strip(): continue
                
                uid = str(hash(text))
                messages.append({
                    "id": uid,
                    "text": text.strip(),
                    "code": extract_code(text),
                    "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                })

            await browser.close()
            return messages
        except Exception as e:
            logging.error(f"❌ خطأ فني في المتصفح: {e}")
            return []

# ==========================================
# 5. المهمة الدورية والتشغيل
# ==========================================
async def job(app):
    sent = load_sent()
    messages = await fetch_sms()
    for msg in messages:
        if msg["id"] in sent: continue
        text = (f"🔔 **OTP Received**\n\n🔑 **Code:** `{msg['code']}`\n"
                f"⏰ **Time:** `{msg['time']}`\n\n💬 **Message:**\n`{msg['text']}`")
        try:
            await app.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
            sent.add(msg["id"])
            save_sent(sent)
        except Exception as e:
            logging.error(f"❌ فشل الإرسال: {e}")

async def main():
    install_playwright()
    app = Application.builder().token(BOT_TOKEN).build()
    await app.initialize()
    await app.bot.get_me() # التأكد من اتصال البوت
    logging.info("🤖 البوت يعمل الآن بنظام الـ Sandbox المعدل...")

    while True:
        try:
            await job(app)
        except Exception as e:
            logging.error(f"⚠️ خطأ في الحلقة: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
