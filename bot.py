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
# 1. الإعدادات
# ==========================================
BOT_TOKEN = "8204515967:AAG6VnSCJ3_-K-XxMRKK2ClB83aW7WZ2dhc"
CHANNEL_ID = -1003678896538

IVASMS_EMAIL = "vipbyr1@gmail.com"
IVASMS_PASSWORD = "svena11.m"

LOGIN_URL = "https://www.ivasms.com/login"
SMS_URL = "https://www.ivasms.com/portal/sms/received/getsms"

CHECK_INTERVAL = 60 
STATE_FILE = "sent_sms.json"

# إعدادات المسارات لـ Railway
BROWSER_PATH = os.path.join(os.getcwd(), "pw-browsers")
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = BROWSER_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ==========================================
# 2. الوظائف المساعدة
# ==========================================
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
# 3. محرك جلب الرسائل المحسن
# ==========================================
async def fetch_sms():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--window-size=1280,800"
            ]
        )
        # محاكاة متصفح حقيقي بالكامل
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        
        page = await context.new_page()
        
        try:
            logging.info("🌐 جاري محاولة فتح الصفحة...")
            # زيادة التايم أوت إلى 90 ثانية لانتظار الكابتشا
            await page.goto(LOGIN_URL, timeout=90000, wait_until="load")
            
            # انتظار عشوائي لمحاكاة سلوك بشري
            await asyncio.sleep(5)

            # التحقق من وجود الكابتشا (Cloudflare أو غيرها)
            if await page.query_selector("iframe") or "Verify" in await page.content():
                logging.warning("⚠️ تم اكتشاف صفحة حماية. جاري الانتظار الإضافي...")
                await asyncio.sleep(15) 

            # محاولة العثور على حقل الإيميل
            email_input = await page.wait_for_selector('input[name="email"]', timeout=45000)
            
            if email_input:
                await page.fill('input[name="email"]', IVASMS_EMAIL)
                await asyncio.sleep(1) # تأخير بسيط بين الإدخالات
                await page.fill('input[name="password"]', IVASMS_PASSWORD)
                
                logging.info("⏳ جاري الضغط على زر الدخول...")
                # الضغط بانتظار الانتقال
                await asyncio.gather(
                    page.click('button[type="submit"]'),
                    page.wait_for_navigation(timeout=60000)
                )

                # التأكد من نجاح الدخول بظهور كلمة Logout
                try:
                    await page.wait_for_selector("text=Logout", timeout=20000)
                    logging.info("✅ تم تسجيل الدخول بنجاح!")
                except:
                    logging.error("❌ فشل الدخول: قد تكون الكابتشا منعت الإرسال.")
                    await page.screenshot(path="debug.png") # حفظ صورة للخطأ
                    await browser.close()
                    return []
            
            # الانتقال لجلب الرسائل
            await page.goto(SMS_URL, timeout=60000, wait_until="networkidle")
            await page.wait_for_selector("div.card-body p", timeout=20000)

            elements = await page.query_selector_all("div.card-body p")
            messages = []
            for el in elements:
                text = await el.inner_text()
                if text.strip():
                    messages.append({
                        "id": str(hash(text)),
                        "text": text.strip(),
                        "code": extract_code(text),
                        "time": datetime.utcnow().strftime("%H:%M:%S")
                    })

            await browser.close()
            return messages

        except Exception as e:
            logging.error(f"⚠️ حدث خطأ أثناء المعالجة: {e}")
            # حفظ صورة عند حدوث أي Timeout لرؤية المشكلة
            await page.screenshot(path="error_timeout.png")
            await browser.close()
            return []

# ==========================================
# 4. تشغيل البوت
# ==========================================
async def job(app):
    sent = load_sent()
    messages = await fetch_sms()
    if not messages: return

    for msg in messages:
        if msg["id"] in sent: continue
        text = f"🔔 **OTP Received**\n\n🔑 **Code:** `{msg['code']}`\n💬 `{msg['text']}`"
        try:
            await app.bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode="Markdown")
            sent.add(msg["id"])
            save_sent(sent)
        except Exception as e:
            logging.error(f"❌ خطأ إرسال: {e}")

async def main():
    # تثبيت المتصفح داخلياً إذا لم يكن موجوداً
    subprocess.run(["python3", "-m", "playwright", "install", "chromium"], check=False)
    
    app = Application.builder().token(BOT_TOKEN).build()
    await app.initialize()
    logging.info("🚀 البوت بدأ العمل بنظام التجاوز الذكي...")

    while True:
        try:
            await job(app)
        except Exception as e:
            logging.error(f"⚠️ خطأ الحلقة الرئيسية: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
