import eventlet
eventlet.monkey_patch()
import bcrypt
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from web_socket_handler import WebSocketHandler
from speech_processor import SpeechProcessor
from dotenv import load_dotenv
from database import Database
from flask_cors import CORS

load_dotenv()
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
CORS(app)

ws_handler = WebSocketHandler()
db = Database()
def on_transcription_result(text: str):
    sid = ws_handler.last_active_sid
    if sid:
        print(f"🔥 Emitting transcription: {text} to SID: {sid}")
        # Use socketio.emit directly - no threading needed with eventlet
        socketio.emit("transcription", {"text": text}, to=sid)
    else:
        print("⚠️ No active SID to emit transcription")


def on_ai_response_result(text: str):
    sid = ws_handler.last_active_sid
    if sid:
        print(f"🔥 Emitting AI Response: {text} to SID: {sid}")
        # Use socketio.emit directly - no threading needed with eventlet
        socketio.emit("ai_response", {"text": text}, to=sid)

        # Also try broadcasting to all clients as a test
        # socketio.emit("ai_response", {"text": text})
    else:
        print("⚠️ No active SID to emit AI response")

processor = SpeechProcessor(on_transcription_result=on_transcription_result, on_ai_response_result=on_ai_response_result)

@socketio.on('connect')
def handle_connect():
    ws_handler.handle_connection(request.sid) # type: ignore
    emit('connected', {'status': 'Connected to speech processing server'})

@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected: {request.sid}") # type: ignore
    # Clean up any resources for this client
    ws_handler.handle_disconnection(request.sid) # type: ignore
    emit('ai_response', {'text': 'Connected to speech processing server'})

@socketio.on("start_audio_stream")
def handle_start_audio(data):
    processor.start_stream()

@socketio.on("audio_data")
def handle_audio(pcm_bytes):
    ws_handler.last_active_sid = request.sid  # type: ignore # Ensure SID is always current

    processor.send_audio(pcm_bytes)  # ✅ Send raw bytes, not base64


@socketio.on("stop_audio_stream")
def handle_stop_audio(data):
    # processor.close_stream()
    processor.process_request(data['text'], data['id'])


@app.route('/api/auth/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        print(email, password)
        #Validation
        if not email or not password:
            return jsonify({'error': 'Email and password required'}), 400

        # # Check if user exists
        exists = db.get_user_account(email, password)
        if not exists:
            #create
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            payload = {
                "email": email,
                "password": hashed_password
            }
            id = db.insert_data("users",payload)
            return jsonify({
                'message': 'User created successfully',
                'user_id': id
            }), 201
        else:
            return jsonify({
                'message': 'User already exists'
            }), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        #Validation
        if not email or not password:
            return jsonify({'error': 'Email and password required'}), 400

        # # Check if user exists
        id = db.get_user_account(email, password)
        if id is not None:
            #create
            return jsonify({
                'user_id': id
            }), 201
        else:
            return jsonify({
                'message': "User doesn't exists",
            }), 403
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    print("Starting Speech Processing WebSocket Server...")
    print("WebSocket events:")
    print("  connect              - Client connection")
    print("  start_audio_stream   - Start audio streaming")
    print("  audio_data           - Send audio chunks")
    print("  stop_audio_stream    - Stop audio streaming")
    print("  disconnect           - Client disconnection")
    print()

    # Keep your existing HTTP endpoints
    socketio.run(app, debug=True, host='0.0.0.0', port=9000)