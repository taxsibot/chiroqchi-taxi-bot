import os
import speech_recognition as sr
from pydub import AudioSegment
from aiogram import Bot, types
import logging
import asyncio

logger = logging.getLogger(__name__)

# Set local FFmpeg paths
FFMPEG_DIR = os.path.join(os.path.dirname(__file__), "ffmpeg_bin")
FFMPEG_PATH = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
FFPROBE_PATH = os.path.join(FFMPEG_DIR, "ffprobe.exe")

# Add to system PATH for this process
if os.path.exists(FFMPEG_DIR):
    os.environ["PATH"] += os.pathsep + FFMPEG_DIR
    AudioSegment.converter = FFMPEG_PATH
    AudioSegment.ffprobe = FFPROBE_PATH
else:
    logger.error(f"CRITICAL ERROR: local FFmpeg directory not found at {FFMPEG_DIR}")

def convert_ogg_to_wav(ogg_path, wav_path):
    """
    Converts .ogg to .wav using pydub (requires ffmpeg).
    """
    try:
        audio = AudioSegment.from_file(ogg_path, format="ogg")
        audio.export(wav_path, format="wav")
        return True
    except Exception as e:
        logger.error(f"Conversion Error (FFmpeg might be missing): {e}")
        return False

async def transcribe_voice(bot: Bot, voice: types.Voice) -> str:
    """
    Downloads voice message, converts to wav, and transcribes using Google Free STT.
    """
    file_id = voice.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    
    os.makedirs('temp', exist_ok=True)
    temp_ogg = f"temp/{file_id}.ogg"
    temp_wav = f"temp/{file_id}.wav"
    
    text = ""
    try:
        await bot.download_file(file_path, temp_ogg)
        
        # 1. Convert OGG to WAV (standard for SpeechRecognition)
        success = await asyncio.to_thread(convert_ogg_to_wav, temp_ogg, temp_wav)
        if success:
            recognizer = sr.Recognizer()
            try:
                # We'll run the entire recognition block in a thread
                def sync_recognize():
                    with sr.AudioFile(temp_wav) as source:
                        audio_data = recognizer.record(source)
                        return recognizer.recognize_google(audio_data, language="uz-UZ")
                
                text = await asyncio.to_thread(sync_recognize)
            except sr.UnknownValueError:
                logger.info("Google STT could not understand audio")
            except sr.RequestError as e:
                logger.error(f"Google STT Request Error: {e}")
            except Exception as e:
                logger.error(f"Transcription Error: {e}")
        else:
            # If conversion failed (likely no ffmpeg)
            text = "ERROR:FFMPEG_MISSING"
    except Exception as e:
        logger.error(f"Error during voice transcription pipeline: {e}")
    finally:
        # Guaranteed Cleanup
        for f in [temp_ogg, temp_wav]:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass
                
    return text
