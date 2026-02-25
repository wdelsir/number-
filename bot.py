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

CHECK_INTERVAL = 60  # زيادة الوقت لتجنب الحظر بسبب الكابتشا
STATE_FILE = "sent_sms.json"

# إعدادات المسارات لـ Railway
BROWSER_PATH = os.path.join(os.getcwd(), "pw-browsers")
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = BROWSER_PATH

# ==========================================
# 2. إعدادات البيئة
# ==========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def load_sent():
    try:
        with open(STATE_FILE, "r") as f: return set(json.load(f))
    except: return set()

def save_sent(data):
    with open(STATE_FILE, "w") as f: json.dump(list(data), f)

def extract_code(text):
    m = re.search(r"\b\d{4,8}\b", text)
    return m.group() if m else "N/A"

# ==========================================
# 3. جلب الرسائل (نسخة مطورة لتجاوز الحماية)
# ==========================================
async def fetch_sms():
    async with async_playwright() as p:
        try:
            # تشغيل المتصفح مع إخفاء سمات البوت
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled", # إخفاء أن المتصفح مبرمج آلياً
                    "--disable-dev-shm-usage"
                ]
            )
            
            # إضافة User-Agent حقيقي ومسح آثار البوت
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            
            page = await context.new_page()
            
            logging.info("🌐 جاري فتح صفحة تسجيل الدخول...")
            # انتظار استقرار الشبكة تماماً (مهم للكابتشا)
            await page.goto(LOGIN_URL, timeout=90000, wait_until="networkidle")

            # التحقق من وجود الكابتشا أو الحماية
            if await page.query_selector('iframe[src*="cloudflare"]') or await page.query_selector("text=Verify you are human"):
                logging.warning("⚠️ تم اكتشاف كابتشا أو حماية Cloudflare! جاري المحاولة...")
                await asyncio.sleep(10) # انتظار بسيط لعل الحماية تتجاوز تلقائياً

            # محاولة ملء البيانات بانتظار أطول
            try:
                await page.wait_for_selector('input[name="email"]', timeout=45000)
                await page.fill('input[name="email"]', IVASMS_EMAIL)
                await page.fill('input[name="password"]', IVASMS_PASSWORD)
                
                logging.info("⏳ جاري الضغط على زر الدخول...")
                await page.click('button[type="submit"]')
                
                # انتظار التحويل بعد تسجيل الدخول
                await page.wait_for_selector("text=Logout", timeout=45000)
                logging.info("✅ تم تسجيل الدخول وتجاوز الحماية")
            except Exception as e:
                logging.error(f"❌ لم يتم العثور على حقول الإدخال، قد تكون الكابتشا منعتنا: {e}")
                await browser.close()
                return []

            # جلب الرسائل
            await page.goto(SMS_URL, wait_until="networkidle")
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
                    "time": datetime.utcnow().strftime("%H:%M:%S")
                })

            await browser.close()
            return messages
        except Exception as e:
            logging.error(f"❌ خطأ فني: {e}")
            return []

# ==========================================
# 4. الوظيفة الدورية
# ==========================================
async def job(app):
    sent = load_sent()
    messages = await fetch_sms()
    if not messages:
        logging.info("ℹ️ لم يتم العثور على رسائل جديدة (أو فشل المتصفح)")
        return

    for msg in messages:
        if msg["id"] in sent: continue
        text = f"🔔 **OTP:** `{msg['code']}`\n💬 `{msg['text']}`"
        try:
            await app.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
            sent.add(msg["id"])
            save_sent(sent)
        except: pass

async def main():
    # التأكد من التثبيت في بيئة السيرفر
    subprocess.run(["python3", "-m", "playwright", "install", "chromium"], check=False)
    
    app = Application.builder().token(BOT_TOKEN).build()
    await app.initialize()
    logging.info("🚀 البوت بدأ العمل بمحرك متطور...")

    while True:
        await job(app)
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
