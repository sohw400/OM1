import base64
import hashlib
import hmac
import json
import logging
import threading
import time
from typing import Callable, Optional, List, Dict
from urllib.parse import quote

from om1_speech import AudioInputStream
from om1_utils import ws
from websocket import create_connection
import websocket

from .singleton import singleton

logger = logging.getLogger(__name__)


@singleton
class XFASRProvider:
    """
    iFlytek Audio Speech Recognition Provider that handles audio streaming and websocket communication.

    This class implements a singleton pattern to manage audio input streaming and websocket
    communication for iFlytek speech recognition services.
    """

    def __init__(
        self,
        app_id: str = "",
        api_key: str = "",
        stream_url: Optional[str] = None,
        device_id: Optional[int] = None,
        microphone_name: Optional[str] = None,
        rate: Optional[int] = 16000,
        chunk: Optional[int] = 1280,
        language_code: Optional[str] = "chinese",  # Changed default to "chinese"
        remote_input: bool = False,
        enable_translation: bool = False,
        enable_role_separation: bool = False,
    ):
        """
        Initialize the XF ASR Provider.

        Parameters
        ----------
        app_id : str
            iFlytek application ID
        api_key : str
            iFlytek API key
        stream_url : str
            The websocket URL for remote audio streaming
        device_id : int
            The device ID of the chosen microphone; used the system default if None
        microphone_name : str
            The name of the microphone to use for audio input
        rate : int
            The audio sample rate for the audio stream (16000 for iFlytek)
        chunk : int
            The audio chunk size for the audio stream (1280 for iFlytek)
        language_code : str
            The language code for language in the audio stream
        remote_input : bool
            If True, the audio input is processed remotely; defaults to False.
        enable_translation : bool
            If True, enable translation feature
        enable_role_separation : bool
            If True, enable role separation feature
        """
        self.running: bool = False
        self.app_id = app_id
        self.api_key = api_key
        self.enable_translation = enable_translation
        self.enable_role_separation = enable_role_separation
        
        # iFlytek WebSocket connection
        self.ws = None
        self.recv_thread = None
        
        # Convert language code to iFlytek format
        self.language_code = self._convert_language_code(language_code)
        
        # Stream WebSocket client for remote audio
        self.stream_ws_client: Optional[ws.Client] = (
            ws.Client(url=stream_url) if stream_url else None
        )
        
        # Initialize audio stream
        self.audio_stream: AudioInputStream = AudioInputStream(
            rate=rate,
            chunk=chunk,
            device=device_id,
            device_name=microphone_name,
            audio_data_callback=self._handle_audio_data,
            language_code=language_code,
            remote_input=remote_input,
        )
        
        # Message callbacks
        self._message_callbacks = []
        
        # End tag for iFlytek
        self.end_tag = "{\"end\": true}"
        
        # Buffer for accumulating partial results
        self._partial_transcript = ""
        self._current_segment_id = -1
        self._last_final_transcript = ""  # Store last final transcript
        self._pending_punctuation = ""  # Buffer for punctuation to append to previous
    
    def _convert_language_code(self, language_code: str) -> str:
        """Convert standard language codes to iFlytek format"""
        language_map = {
            # Standard codes
            "zh-CN": "cn",
            "cmn-Hans-CN": "cn",
            "en-US": "en",
            "en": "en",
            "ja-JP": "ja",
            "ko-KR": "ko",
            # Friendly names
            "chinese": "cn",
            "english": "en",
            "japanese": "ja",
            "korean": "ko",
            # iFlytek codes (pass through)
            "cn": "cn",
            "ja": "ja",
            "ko": "ko",
        }
        return language_map.get(language_code, "cn")  # Default to Chinese
    
    def _connect_to_xfyun(self):
        """Establish connection to iFlytek ASR service"""
        base_url = "ws://rtasr.xfyun.cn/v1/ws"
        ts = str(int(time.time()))
        
        # Generate signature according to iFlytek docs
        # 1. Create base string: appid + ts
        base_string = self.app_id + ts
        
        # 2. MD5 hash the base string
        md5 = hashlib.md5()
        md5.update(base_string.encode('utf-8'))
        md5_string = md5.hexdigest()
        
        # 3. HMAC-SHA1 using api_key as key, then base64 encode
        signa = hmac.new(
            self.api_key.encode('utf-8'),
            md5_string.encode('utf-8'),
            hashlib.sha1
        ).digest()
        signa = base64.b64encode(signa).decode('utf-8')
        
        # Build URL with parameters
        params = []
        params.append(f"appid={self.app_id}")
        params.append(f"ts={ts}")
        params.append(f"signa={quote(signa)}")
        
        # Add language parameter
        params.append(f"lang={self.language_code}")
        
        # Add optional parameters
        if self.enable_translation:
            params.append("transType=normal")
            params.append("transStrategy=2")  # Return intermediate results
            params.append("targetLang=en")  # Default target language
        
        if self.enable_role_separation:
            params.append("roleType=2")
        
        # Build final URL
        url = base_url + "?" + "&".join(params)
        
        logger.info(f"Connecting to iFlytek with language: {self.language_code}, translation: {self.enable_translation}")
        self.ws = create_connection(url)
        
        # Start receive thread
        self.recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.recv_thread.start()
    
    def _parse_recognition_result(self, data_str: str) -> Dict:
        """
        Parse the recognition result from iFlytek's complex format.
        
        Parameters
        ----------
        data_str : str
            The JSON string from the 'data' field
            
        Returns
        -------
        Dict
            Parsed result with transcript and metadata
        """
        try:
            data = json.loads(data_str)
            
            # Check if this is a translation result
            if data.get("biz") == "trans":
                return {
                    "type": "translation",
                    "source": data.get("src", ""),
                    "translation": data.get("dst", ""),
                    "is_final": data.get("isEnd", False),
                    "segment_id": data.get("segId", 0),
                    "start_time": data.get("bg", 0),
                    "end_time": data.get("ed", 0)
                }
            
            # Regular transcription result
            result = {
                "type": "transcription",
                "words": [],
                "transcript": "",
                "segment_id": data.get("seg_id", 0),
                "is_final": False,
                "role_id": 0
            }
            
            # Parse the nested structure
            cn = data.get("cn", {})
            st = cn.get("st", {})
            
            # Get timing information
            result["start_time"] = int(st.get("bg", "0"))
            result["end_time"] = int(st.get("ed", "0"))
            
            # Check if this is final result (type "0") or intermediate (type "1")
            result["is_final"] = (st.get("type", "1") == "0")
            
            # Extract words and maintain proper order
            rt = st.get("rt", [])
            words = []
            transcript_parts = []
            
            for rt_item in rt:
                ws = rt_item.get("ws", [])
                
                # Check for role separation
                if "rl" in rt_item and self.enable_role_separation:
                    result["role_id"] = rt_item.get("rl", 0)
                
                for word_item in ws:
                    cw = word_item.get("cw", [])
                    for char_item in cw:
                        word = char_item.get("w", "")
                        word_type = char_item.get("wp", "n")
                        
                        if word:
                            word_info = {
                                "word": word,
                                "type": word_type,  # n-normal, s-filler, p-punctuation
                                "start_time": result["start_time"] + word_item.get("wb", 0) * 10,
                                "end_time": result["start_time"] + word_item.get("we", 0) * 10
                            }
                            words.append(word_info)
                            transcript_parts.append(word)
            
            # Join all parts to create the transcript
            result["transcript"] = "".join(transcript_parts)
            result["words"] = words
            
            return result
            
        except Exception as e:
            logger.error(f"Error parsing recognition result: {str(e)}")
            return {"type": "error", "error": str(e)}
    
    def _handle_audio_data(self, audio_json: str):
        """
        Handle audio data from AudioInputStream and send to iFlytek.
        
        Parameters
        ----------
        audio_json : str
            JSON string containing base64 encoded audio data
        """
        if not self.running or not self.ws:
            return
        
        try:
            # Parse the audio data
            audio_data = json.loads(audio_json)
            
            # Decode base64 audio
            audio_bytes = base64.b64decode(audio_data["audio"])
            
            # Send raw audio bytes to iFlytek
            self.ws.send(audio_bytes)
            
        except Exception as e:
            logger.error(f"Error handling audio data: {str(e)}")
    
    def _receive_loop(self):
        """Receive and process results from iFlytek"""
        try:
            while self.running and self.ws:
                try:
                    result = self.ws.recv()
                    if len(result) == 0:
                        logger.info("Received empty result, connection may be closing")
                        break
                    
                    result_dict = json.loads(result)
                    
                    # Check action type
                    action = result_dict.get("action", "")
                    
                    if action == "started":
                        logger.info(f"iFlytek handshake success")
                        # Send connection success message
                        self._send_to_callbacks(json.dumps({
                            "type": "connection",
                            "message": "Connected to iFlytek ASR",
                            "sid": result_dict.get("sid", "")
                        }))
                    
                    elif action == "result":
                        # Check if request was successful
                        if result_dict.get("code", "0") != "0":
                            logger.error(f"iFlytek error code: {result_dict.get('code')}, desc: {result_dict.get('desc')}")
                            continue
                        
                        # Parse the complex data structure
                        data_str = result_dict.get("data", "")
                        if data_str:
                            parsed_result = self._parse_recognition_result(data_str)
                            
                            if parsed_result["type"] == "transcription":
                                # Handle transcription result
                                transcript = parsed_result["transcript"]
                                seg_id = parsed_result["segment_id"]
                                
                                # Check if transcript starts with punctuation
                                if transcript and transcript[0] in "。！？，、；：,.!?;:":
                                    # Extract leading punctuation
                                    leading_punct = ""
                                    i = 0
                                    while i < len(transcript) and transcript[i] in "。！？，、；：,.!?;:":
                                        leading_punct += transcript[i]
                                        i += 1
                                    
                                    # If we have a previous final transcript, append punctuation to it
                                    if self._last_final_transcript and leading_punct:
                                        # Send updated previous transcript with punctuation
                                        updated_message = json.dumps({
                                            "asr_reply": self._last_final_transcript + leading_punct,
                                            "provider": "xfyun",
                                            "is_final": True,
                                            "segment_id": self._current_segment_id,
                                            "update_previous": True  # Flag to indicate this updates the previous
                                        }, ensure_ascii=False)
                                        
                                        logger.info(f"Updated previous transcript with punctuation: {self._last_final_transcript + leading_punct}")
                                        self._send_to_callbacks(updated_message)
                                    
                                    # Remove leading punctuation from current transcript
                                    transcript = transcript[i:].strip()
                                
                                # Only process non-empty transcripts
                                if transcript:
                                    # Handle partial vs final results
                                    if parsed_result["is_final"]:
                                        # Final result for this segment
                                        self._last_final_transcript = transcript
                                        self._current_segment_id = seg_id
                                        
                                        message = json.dumps({
                                            "asr_reply": transcript,
                                            "provider": "xfyun",
                                            "is_final": True,
                                            "segment_id": seg_id,
                                            "start_time": parsed_result["start_time"],
                                            "end_time": parsed_result["end_time"],
                                            "words": parsed_result.get("words", []),
                                            "role_id": parsed_result.get("role_id", 0)
                                        }, ensure_ascii=False)
                                        
                                        logger.info(f"Final transcript (seg {seg_id}): {transcript}")
                                    else:
                                        # Intermediate result
                                        if seg_id > self._current_segment_id:
                                            # New segment started
                                            self._current_segment_id = seg_id
                                            self._partial_transcript = transcript
                                        else:
                                            # Update current segment
                                            self._partial_transcript = transcript
                                        
                                        message = json.dumps({
                                            "asr_reply": transcript,
                                            "provider": "xfyun",
                                            "is_final": False,
                                            "segment_id": seg_id,
                                            "start_time": parsed_result["start_time"]
                                        }, ensure_ascii=False)
                                        
                                        logger.debug(f"Partial transcript (seg {seg_id}): {transcript}")
                                    
                                    self._send_to_callbacks(message)
                            
                            elif parsed_result["type"] == "translation":
                                # Handle translation result
                                message = json.dumps({
                                    "type": "translation",
                                    "source": parsed_result["source"],
                                    "translation": parsed_result["translation"],
                                    "is_final": parsed_result["is_final"],
                                    "segment_id": parsed_result["segment_id"],
                                    "provider": "xfyun"
                                }, ensure_ascii=False)
                                
                                logger.info(f"Translation: {parsed_result['source']} -> {parsed_result['translation']}")
                                self._send_to_callbacks(message)
                    
                    elif action == "error":
                        error_desc = result_dict.get("desc", "Unknown error")
                        logger.error(f"iFlytek error: {error_desc}")
                        self._send_to_callbacks(json.dumps({
                            "type": "error",
                            "message": f"ASR error: {error_desc}",
                            "code": result_dict.get("code", ""),
                            "sid": result_dict.get("sid", "")
                        }))
                        break
                        
                except websocket.WebSocketConnectionClosedException:
                    logger.info("iFlytek WebSocket connection closed")
                    break
                except Exception as e:
                    logger.error(f"Error in receive loop: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Fatal error in receive loop: {str(e)}")
        finally:
            self._cleanup_connection()
    
    def _send_to_callbacks(self, message: str):
        """Send message to all registered callbacks"""
        for callback in self._message_callbacks:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Error in message callback: {str(e)}")
    
    def _cleanup_connection(self):
        """Clean up WebSocket connection"""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None
    
    def register_message_callback(self, message_callback: Optional[Callable]):
        """
        Register a callback for processing ASR results.

        Parameters
        ----------
        callback : callable
            The callback function to process ASR results.
        """
        if message_callback and message_callback not in self._message_callbacks:
            self._message_callbacks.append(message_callback)
            logger.info("Registered message callback")

    def start(self):
        """
        Start the ASR provider.

        Initializes and starts the websocket connection, audio stream, and processing threads
        if not already running.
        """
        if self.running:
            logger.warning("XF ASR provider is already running")
            return

        self.running = True
        
        try:
            # Connect to iFlytek
            self._connect_to_xfyun()
            
            # Start audio stream
            self.audio_stream.start()
            
            # Setup remote stream if configured
            if self.stream_ws_client:
                self.stream_ws_client.start()
                self.audio_stream.register_audio_data_callback(
                    self.stream_ws_client.send_message
                )
                # Register the audio stream to fill the buffer for remote input
                if self.audio_stream.remote_input:
                    self.stream_ws_client.register_message_callback(
                        self.audio_stream.fill_buffer_remote
                    )
            
            logger.info("XF ASR provider started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start XF ASR provider: {str(e)}")
            self.running = False
            raise

    def stop(self):
        """
        Stop the ASR provider.

        Stops the audio stream and websocket connections, and sets the running state to False.
        """
        logger.info("Stopping XF ASR provider...")
        self.running = False
        
        # Send end tag to iFlytek
        if self.ws:
            try:
                self.ws.send(self.end_tag.encode('utf-8'))
                time.sleep(0.5)  # Give time for end tag to be sent
            except Exception as e:
                logger.error(f"Error sending end tag: {str(e)}")
        
        # Stop audio stream
        self.audio_stream.stop()
        
        # Stop stream WebSocket client
        if self.stream_ws_client:
            self.stream_ws_client.stop()
        
        # Clean up connection
        self._cleanup_connection()
        
        # Wait for receive thread
        if self.recv_thread and self.recv_thread.is_alive():
            self.recv_thread.join(timeout=2.0)
        
        logger.info("XF ASR provider stopped")
