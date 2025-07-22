import asyncio
import os
import threading
import websockets
import json
import time
import base64

from action import Action
from prompt_dict import prompt_dict
from ai_generator import AIGenerator


class SpeechProcessor:
    def __init__(self, on_transcription_result, on_ai_response_result):
        self.ws = None
        self.loop = None
        self.thread = None
        self.api_key = os.getenv("ASSEMBLYAI_API_TOKEN")
        self.is_connected = False
        self.is_streaming = False
        self._stop_event = None
        self.on_transcription_result = on_transcription_result
        self.on_ai_response_result = on_ai_response_result
        self.action = Action()

    def start_stream(self):
        if self.is_streaming:
            print("Stream already running")
            return

        print("Starting audio stream...")
        self.is_streaming = True
        self._stop_event = threading.Event()

        # Create and start the thread
        self.thread = threading.Thread(target=self._run_ws_loop, daemon=False)
        self.thread.start()

        # Wait a bit for connection to establish
        time.sleep(10)

        if not self.is_connected:
            print("Failed to establish connection within timeout")

    def _run_ws_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            # Run the connection coroutine
            self.loop.run_until_complete(self._connect_and_run())
        except Exception as e:
            print(f"WebSocket loop error: {e}")
        finally:
            print("WebSocket loop ended")
            self.is_streaming = False
            self.is_connected = False

    async def _connect_and_run(self):
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries and not self._stop_event.is_set(): # type: ignore
            try:
                # Updated to new Universal Streaming endpoint
                url = "wss://streaming.assemblyai.com/v3/ws?sample_rate=16000&word_boost=[]&encoding=pcm_s16le"
                headers = {"Authorization": self.api_key}

                print(f"Attempting to connect to AssemblyAI Universal Streaming... (attempt {retry_count + 1})")
                print(f"URL: {url}")

                async with websockets.connect(
                        url,
                        additional_headers=headers, # type: ignore
                        ping_interval=20,  # Send ping every 20 seconds
                        ping_timeout=10,  # Wait 10 seconds for pong
                        close_timeout=10  # Wait 10 seconds for close
                ) as websocket:
                    self.ws = websocket
                    self.is_connected = True
                    print("Successfully connected to AssemblyAI Universal Streaming WebSocket")

                    # For the new API, we don't need to send initial configuration
                    # The configuration is passed in the URL parameters
                    print("Using Universal Streaming API - no initial config needed")

                    # Start receiving messages
                    await self._receive_messages(websocket)

            except websockets.exceptions.InvalidStatusCode as e: # type: ignore
                print(f"Invalid status code: {e}")
                if e.status_code == 401:
                    print("Authentication failed - check your API key")
                    break
            except websockets.exceptions.ConnectionClosedError as e:
                print(f"Connection closed: {e}")
            except Exception as e:
                print(f"Connection error: {e}")

            retry_count += 1
            if retry_count < max_retries and not self._stop_event.is_set(): # type: ignore
                wait_time = 2 ** retry_count  # Exponential backoff
                print(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)

        self.is_connected = False
        print("Connection attempts exhausted or stopped")

    async def _receive_messages(self, websocket):
        try:
            while not self._stop_event.is_set(): # type: ignore
                # Wait for message with timeout
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    await self._handle_message(message)
                except asyncio.TimeoutError:
                    # Check if we should continue listening
                    continue
                except websockets.exceptions.ConnectionClosed:
                    print("WebSocket connection closed by server")
                    break

        except Exception as e:
            print(f"Error in receive loop: {e}")

    async def _handle_message(self, message):
        try:
            print(f"Received raw message: {message}")
            msg = json.loads(message)

            message_type = msg.get("type", "unknown")
            print(f"Message type: {message_type}")

            if message_type == "Begin":
                print("✅ Session began successfully")
                session_id = msg.get("id", "unknown")
                print(f"Session ID: {session_id}")

            elif message_type == "Turn":
                text = msg.get('transcript', '')
                confidence = msg['words'][-1].get("confidence", 0)
                if text.strip():
                    print(f"✅ Final transcript: '{text}' (confidence: {confidence:.2f})")
                    # TODO: Here you can emit back to client or send to LLM
                    if text:

                        self.on_transcription_result(text)
                        # self.process_request(text)


            elif message_type == "SessionTerminated":
                print("Session terminated by server")

            elif message_type == "Error":
                error_msg = msg.get("error", "Unknown error")
                print(f"❌ AssemblyAI Error: {error_msg}")

            else:
                print(f"📥 Unhandled message: {msg['words']}")

        except json.JSONDecodeError as e:
            print(f"Failed to parse message as JSON: {e}")
        except Exception as e:
            print(f"Error handling message: {e}")

    def send_audio(self, base64_audio):
        if not self.is_connected or not self.ws:
            print("❌ WebSocket not connected, cannot send audio")
            return False

        if not base64_audio or not base64_audio.strip():
            print("Empty audio data received")
            return False

        try:
            # Validate base64 format
            try:
                decoded = base64.b64decode(base64_audio)
            except Exception as e:
                print(f"Invalid base64 audio data: {e}")
                return False

            # For Universal Streaming API, send the base64 string directly
            # No need to wrap in JSON - just send the base64 string
            if self.loop and not self.loop.is_closed():
                future = asyncio.run_coroutine_threadsafe(
                    self.ws.send(base64_audio),  # Send base64 directly, not wrapped in JSON
                    self.loop
                )

                # Wait for completion with timeout
                future.result(timeout=2.0)

                return True
            else:
                print("Event loop is not running")
                return False

        except asyncio.TimeoutError:
            print("⏰ Timeout sending audio data")
            return False
        except Exception as e:
            print(f"❌ Error sending audio: {e}")
            return False

    def close_stream(self):
        print("🔴 Closing audio stream...")

        if self._stop_event:
            self._stop_event.set()

        if self.ws and self.is_connected:
            try:
                # For Universal Streaming API, just close the connection
                # No need to send termination message
                if self.loop and not self.loop.is_closed():
                    future = asyncio.run_coroutine_threadsafe(
                        self.ws.close(),
                        self.loop
                    )
                    future.result(timeout=2.0)
                    print("Connection closed")

            except Exception as e:
                print(f"Error during cleanup: {e}")

        # Wait for thread to finish
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                print("Thread did not terminate gracefully")

        self.is_connected = False
        self.is_streaming = False
        print("✅ Stream closed successfully")

    def get_status(self):
        return {
            "is_connected": self.is_connected,
            "is_streaming": self.is_streaming,
            "has_api_key": bool(self.api_key),
            "thread_alive": self.thread.is_alive() if self.thread else False
        }

    def process_request(self, text, id):
        ai_generator = AIGenerator()
        full_prompt = f"{prompt_dict.get('INTENT_PROMPT')} {text}"

        get_intent = ai_generator.generate_response(full_prompt)
        response = self.action.take_action(get_intent, text, id)
        self.on_ai_response_result(response)