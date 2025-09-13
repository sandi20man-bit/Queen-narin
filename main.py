import os
import pytz
import random
import html
import tempfile
import requests
import io
import aiohttp
import asyncio
from datetime import datetime, time
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Import keep-alive system
try:
    from keep_alive import start_keep_alive, stop_keep_alive
    KEEP_ALIVE_AVAILABLE = True
    print("✅ Keep-alive system tersedia")
except ImportError:
    KEEP_ALIVE_AVAILABLE = False
    print("⚠️ Keep-alive system tidak tersedia")

# In-memory storage untuk video file_id (untuk random video)
video_file_ids = []

# Auto-delete helper function
async def auto_delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id, message_id, delay_seconds=7):
    """Hapus pesan otomatis setelah delay tertentu (default 7 detik)"""
    try:
        await asyncio.sleep(delay_seconds)
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        print(f"🗑️ Auto-deleted message {message_id} from chat {chat_id}")
    except Exception as e:
        # Pesan mungkin sudah dihapus atau tidak bisa dihapus
        print(f"⚠️ Could not auto-delete message {message_id}: {e}")

async def schedule_message_deletion(context: ContextTypes.DEFAULT_TYPE, message, delay_seconds=7):
    """Schedule pesan untuk dihapus dengan delay custom (default 7 detik)"""
    if message and message.message_id and message.chat:
        # Jalankan auto-delete dalam background task
        asyncio.create_task(auto_delete_message(context, message.chat.id, message.message_id, delay_seconds))
        print(f"⏰ Scheduled deletion for message {message.message_id} in {delay_seconds} seconds")

# Centralized ephemeral messaging functions
async def send_ephemeral_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text, parse_mode='HTML', reply_markup=None, is_reply=True):
    """Send ephemeral text message that auto-deletes in 7 seconds"""
    try:
        sent_message = None
        if is_reply and update.message:
            sent_message = await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        elif update.callback_query and update.callback_query.message:
            sent_message = await context.bot.send_message(
                chat_id=update.callback_query.message.chat.id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
        elif update.effective_chat:
            sent_message = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
        
        # Schedule for auto-delete
        if sent_message:
            await schedule_message_deletion(context, sent_message)
            print(f"✅ Ephemeral text sent: {text[:50]}...")
        
        return sent_message
        
    except Exception as e:
        print(f"❌ Error sending ephemeral text: {e}")
        return None

async def send_ephemeral_voice(update: Update, context: ContextTypes.DEFAULT_TYPE, text):
    """Send ephemeral voice message that auto-deletes in 7 seconds"""
    voice_file = None
    try:
        # Generate voice file dengan ElevenLabs
        voice_file = await create_elevenlabs_voice(text)
        
        if voice_file and update.effective_chat:
            # Send "upload_voice" action
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, 
                action="upload_voice"
            )
            
            # Kirim voice message dan capture response
            with open(voice_file, 'rb') as voice:
                sent_voice = await context.bot.send_voice(
                    chat_id=update.effective_chat.id,
                    voice=voice
                )
            
            # Schedule voice message for auto-delete (20 detik untuk voice)
            if sent_voice:
                await schedule_message_deletion(context, sent_voice, delay_seconds=20)
                print(f"✅ Ephemeral voice sent and scheduled for deletion: {text[:50]}...")
            
            return sent_voice
        else:
            print("❌ Gagal membuat ephemeral voice message")
            return None
            
    except Exception as e:
        print(f"❌ Error sending ephemeral voice: {e}")
        return None
    finally:
        # Cleanup temporary file
        if voice_file and os.path.exists(voice_file):
            try:
                os.unlink(voice_file)
            except:
                pass

async def send_ephemeral_voice_with_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE, text, fallback_text=None):
    """Send ephemeral voice with text fallback - both auto-delete"""
    if not fallback_text:
        fallback_text = text
    
    # Try to send ephemeral voice first
    voice_message = await send_ephemeral_voice(update, context, text)
    
    # If voice fails, send ephemeral text fallback
    if not voice_message:
        print("🔄 Voice failed, sending ephemeral text fallback")
        await send_ephemeral_text(update, context, fallback_text)
        return False
    
    return True

# ElevenLabs configuration
ELEVENLABS_API_KEY = None
ELEVENLABS_API_KEY_BACKUP = None
ELEVENLABS_API_KEY_BACKUP2 = None
ELEVENLABS_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # Bella - suara wanita natural
ELEVENLABS_API_KEYS = []  # List untuk menyimpan semua API keys

def init_elevenlabs():
    """Initialize ElevenLabs API dengan sistem backup keys"""
    global ELEVENLABS_API_KEYS, ELEVENLABS_VOICE_ID
    
    if not ELEVENLABS_API_KEYS:
        print("⚠️ ElevenLabs API keys belum diset, voice response tidak tersedia")
        print("💡 Edit file .aldy dan isi ELEVENLABS_API_KEY (dan backup) untuk aktifkan fitur suara")
        return False
    
    # Test setiap API key
    valid_keys = []
    for i, api_key in enumerate(ELEVENLABS_API_KEYS):
        try:
            url = "https://api.elevenlabs.io/v1/voices"
            headers = {"xi-api-key": api_key}
            response = requests.get(url, headers=headers, timeout=5)
            
            key_type = "utama" if i == 0 else f"backup {i}"
            if response.status_code == 200:
                print(f"✅ API {key_type} valid dan berfungsi")
                valid_keys.append(api_key)
            else:
                print(f"❌ API {key_type} tidak valid: {response.status_code}")
                
        except Exception as e:
            key_type = "utama" if i == 0 else f"backup {i}"
            print(f"❌ Error testing API {key_type}: {e}")
    
    # Update ELEVENLABS_API_KEYS dengan hanya keys yang valid
    ELEVENLABS_API_KEYS = valid_keys
    
    if ELEVENLABS_API_KEYS:
        print(f"🎤 Bot siap dengan suara wanita ElevenLabs! ({len(ELEVENLABS_API_KEYS)} API key aktif)")
        return True
    else:
        print("❌ Tidak ada ElevenLabs API key yang valid")
        return False

async def check_elevenlabs_quota(api_key=None):
    """Check ElevenLabs API quota dan sisa credit dengan support untuk backup keys"""
    global ELEVENLABS_API_KEYS
    
    # Jika api_key spesifik diberikan, gunakan itu
    if api_key:
        keys_to_try = [api_key]
    else:
        # Gunakan semua keys yang tersedia
        keys_to_try = ELEVENLABS_API_KEYS
    
    if not keys_to_try:
        return None
    
    # Coba setiap API key sampai ada yang berhasil
    for i, key in enumerate(keys_to_try):
        try:
            url = "https://api.elevenlabs.io/v1/user/subscription"
            headers = {"xi-api-key": key}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        used_chars = data.get('character_count', 0)
                        total_chars = data.get('character_limit', 0)
                        remaining_chars = total_chars - used_chars
                        tier = data.get('tier', 'Unknown')
                        reset_unix = data.get('next_character_count_reset_unix', 0)
                        
                        # Convert unix timestamp to readable date
                        if reset_unix:
                            reset_date = datetime.fromtimestamp(reset_unix, pytz.timezone(TIMEZONE))
                            reset_str = reset_date.strftime("%d/%m/%Y %H:%M")
                        else:
                            reset_str = "Unknown"
                        
                        key_type = "utama" if i == 0 else f"backup {i}"
                        print(f"✅ Quota check berhasil menggunakan API {key_type}")
                        
                        return {
                            'used': used_chars,
                            'total': total_chars,
                            'remaining': remaining_chars,
                            'tier': tier,
                            'reset_date': reset_str,
                            'percentage_used': round((used_chars / total_chars * 100), 1) if total_chars > 0 else 0,
                            'api_key_used': key,
                            'api_key_type': key_type
                        }
                    else:
                        error_text = await response.text()
                        key_type = "utama" if i == 0 else f"backup {i}"
                        print(f"❌ API {key_type} error: {response.status} - {error_text[:100]}")
                        continue
                        
        except Exception as e:
            key_type = "utama" if i == 0 else f"backup {i}"
            print(f"❌ Error API {key_type}: {e}")
            continue
    
    print("❌ Semua API key ElevenLabs gagal atau habis quota")
    return None

async def create_elevenlabs_voice(text):
    """Convert text menjadi voice menggunakan ElevenLabs API dengan backup keys"""
    global ELEVENLABS_API_KEYS, ELEVENLABS_VOICE_ID
    
    if not ELEVENLABS_API_KEYS:
        print("❌ Tidak ada ElevenLabs API key yang tersedia")
        return None
    
    # Coba setiap API key sampai ada yang berhasil
    for i, api_key in enumerate(ELEVENLABS_API_KEYS):
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": api_key
            }
            
            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.75,
                    "similarity_boost": 0.75,
                    "style": 0.5,
                    "use_speaker_boost": True
                }
            }
            
            # Log request attempt
            key_type = "utama" if i == 0 else f"backup {i}"
            print(f"🎤 Mencoba voice dengan API {key_type}: {text[:50]}...")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        # Buat temporary file untuk voice
                        content = await response.read()
                        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
                            temp_file.write(content)
                            print(f"✅ Voice berhasil dibuat dengan API {key_type}: {temp_file.name}")
                            return temp_file.name
                            
                    elif response.status == 401:
                        error_text = await response.text()
                        print(f"❌ API {key_type} tidak valid atau expired: {error_text[:100]}")
                        continue
                        
                    elif response.status == 429:
                        error_text = await response.text()
                        print(f"❌ API {key_type} rate limit atau quota habis: {error_text[:100]}")
                        continue
                        
                    else:
                        error_text = await response.text()
                        print(f"❌ API {key_type} error {response.status}: {error_text[:100]}")
                        continue
                        
        except Exception as e:
            key_type = "utama" if i == 0 else f"backup {i}"
            print(f"❌ Error API {key_type}: {e}")
            continue
    
    print("❌ Semua API key ElevenLabs gagal untuk voice generation")
    return None

async def send_voice_response(update: Update, context: ContextTypes.DEFAULT_TYPE, text, caption=None):
    """Helper function untuk mengirim voice message dengan ElevenLabs - FIXED: now captures and schedules voice for auto-delete"""
    voice_file = None
    try:
        # Generate voice file dengan ElevenLabs (now async)
        voice_file = await create_elevenlabs_voice(text)
        
        if voice_file:
            # Send "upload_voice" action
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, 
                action="upload_voice"
            )
            
            # Kirim voice message dan capture response untuk auto-delete
            with open(voice_file, 'rb') as voice:
                sent_voice = await context.bot.send_voice(
                    chat_id=update.effective_chat.id,
                    voice=voice
                )
            
            # FIXED: Schedule voice message for auto-deletion (20 detik untuk voice)
            if sent_voice:
                await schedule_message_deletion(context, sent_voice, delay_seconds=20)
                print(f"✅ Voice message sent and scheduled for deletion: {text[:50]}...")
            
            return True
        else:
            print("❌ Gagal membuat voice message")
            return False
            
    except Exception as e:
        print(f"❌ Error mengirim voice message: {e}")
        return False
    finally:
        # Cleanup temporary file
        if voice_file and os.path.exists(voice_file):
            try:
                os.unlink(voice_file)
            except:
                pass


def load_config():
    """
    Fungsi untuk memuat konfigurasi dari file .aldy
    Jika file .aldy tidak ada, akan mencoba .env, lalu environment variables
    """
    # Coba load dari file .aldy terlebih dahulu
    if os.path.exists('.aldy'):
        load_dotenv('.aldy')
        print("✅ Konfigurasi dimuat dari file .aldy")
    elif os.path.exists('.env'):
        load_dotenv('.env')
        print("✅ Konfigurasi dimuat dari file .env")
    else:
        print("ℹ️ File konfigurasi tidak ditemukan, menggunakan environment variables")
    
    # Ambil konfigurasi dari environment variables
    bot_token = os.getenv("BOT_TOKEN")
    chat_id_str = os.getenv("CHAT_ID")
    timezone = os.getenv("TIMEZONE", "Asia/Jakarta")
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
    elevenlabs_backup = os.getenv("ELEVENLABS_API_KEY_BACKUP")
    elevenlabs_backup2 = os.getenv("ELEVENLABS_API_KEY_BACKUP2")
    elevenlabs_voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    
    # Validasi CHAT_ID - bisa berupa angka atau username channel (@channelname)
    chat_id = None
    if chat_id_str:
        if chat_id_str.startswith('@'):
            # Jika format username channel/grup
            chat_id = chat_id_str
            print(f"✅ Menggunakan channel username: {chat_id_str}")
        else:
            # Jika format angka ID
            try:
                chat_id = int(chat_id_str)
                print(f"✅ Menggunakan chat ID: {chat_id}")
            except ValueError:
                print(f"❌ CHAT_ID tidak valid: {chat_id_str}")
    
    # CHAT_ID wajib diisi untuk keamanan
    if not chat_id:
        print("❌ CHAT_ID wajib diisi di file .aldy untuk keamanan!")
        print("Bot tidak akan berjalan tanpa konfigurasi grup target yang jelas.")
        return None, None, timezone, None
    
    # Set ElevenLabs API keys global
    global ELEVENLABS_API_KEY, ELEVENLABS_API_KEY_BACKUP, ELEVENLABS_API_KEY_BACKUP2, ELEVENLABS_VOICE_ID, ELEVENLABS_API_KEYS
    ELEVENLABS_API_KEY = elevenlabs_key
    ELEVENLABS_API_KEY_BACKUP = elevenlabs_backup
    ELEVENLABS_API_KEY_BACKUP2 = elevenlabs_backup2
    
    # Set voice ID jika ada
    if elevenlabs_voice_id and elevenlabs_voice_id != "your_elevenlabs_voice_id_here":
        ELEVENLABS_VOICE_ID = elevenlabs_voice_id
    
    # Build list API keys yang valid (tidak kosong dan bukan placeholder)
    ELEVENLABS_API_KEYS = []
    for key in [elevenlabs_key, elevenlabs_backup, elevenlabs_backup2]:
        if key and key.strip() and key != "your_elevenlabs_api_key_here" and key != "your_backup_elevenlabs_api_key_here" and key != "your_backup2_elevenlabs_api_key_here":
            ELEVENLABS_API_KEYS.append(key.strip())
    
    if ELEVENLABS_API_KEYS:
        print(f"✅ {len(ELEVENLABS_API_KEYS)} ElevenLabs API key(s) berhasil dimuat (1 utama + {len(ELEVENLABS_API_KEYS)-1} backup)")
    else:
        print("⚠️ Tidak ada ElevenLabs API key yang valid ditemukan")
    
    # Validasi TIMEZONE
    try:
        pytz.timezone(timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        print(f"❌ TIMEZONE tidak valid: {timezone}, menggunakan Asia/Jakarta")
        timezone = "Asia/Jakarta"
    
    return bot_token, chat_id, timezone, elevenlabs_key

def create_config_template():
    """
    Fungsi untuk membuat template file .aldy jika belum ada
    """
    if not os.path.exists('.aldy'):
        template_content = """# Konfigurasi Bot Telegram Absensi Harian
# ===========================================
# 
# Petunjuk Pengisian:
# 1. BOT_TOKEN: Dapatkan dari @BotFather di Telegram
# 2. CHAT_ID: ID grup/channel tempat bot mengirim pesan 
# 3. TIMEZONE: Zona waktu untuk scheduler (default: Asia/Jakarta)

# Token Bot Telegram (wajib diisi)
BOT_TOKEN=your_bot_token_here

# Chat ID grup/channel target (wajib diisi)  
CHAT_ID=@vipdyy011

# Timezone untuk scheduler absensi
TIMEZONE=Asia/Jakarta"""
        
        try:
            with open('.aldy', 'w', encoding='utf-8') as f:
                f.write(template_content)
            print("✅ Template file .aldy berhasil dibuat")
            print("📝 Silakan edit file .aldy dan isi dengan konfigurasi yang benar")
        except Exception as e:
            print(f"❌ Gagal membuat template .aldy: {e}")
    else:
        print("ℹ️ File .aldy sudah ada")

# Placeholder untuk konfigurasi - akan diload di main()
BOT_TOKEN = None
CHAT_ID = None
TIMEZONE = "Asia/Jakarta"

# Authorization constants
AUTHORIZED_USER_ID = 6141653876  # Only this user ID can interact with bot

# Dictionary untuk menyimpan data absensi
# Format: {tanggal: {user_id: {"nama": str, "status": "Hadir"/"Tidak Hadir", "waktu": datetime}}}
attendance = {}

# Authorization helper function
async def check_authorization(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check if user is authorized to use bot features"""
    # Allow messages from target channel/group (for scheduled attendance, video collection, etc)
    if update.effective_chat and CHAT_ID:
        # Check if message is from target channel/group
        if isinstance(CHAT_ID, int) and update.effective_chat.id == CHAT_ID:
            return True
        elif isinstance(CHAT_ID, str) and CHAT_ID.startswith('@'):
            if update.effective_chat.username and f"@{update.effective_chat.username}".lower() == CHAT_ID.lower():
                return True
        elif str(update.effective_chat.id) == str(CHAT_ID):
            return True
    
    # Allow authorized user ID
    if update.effective_user and update.effective_user.id == AUTHORIZED_USER_ID:
        return True
    
    # Unauthorized - send friendly voice response
    if update.effective_user:
        unauthorized_text = (
            f"Maaf sayang, bot ini khusus untuk owner saja ya. "
            f"Bot absensi pribadi yang tidak bisa diakses user lain. "
            f"Terima kasih sudah coba, tapi akses dibatasi untuk keamanan. "
            f"Have a nice day!"
        )
        
        # Send unauthorized message (will auto-delete in 7 seconds)
        await send_ephemeral_voice_with_fallback(update, context, unauthorized_text)
        print(f"🚫 Unauthorized access attempt from user {update.effective_user.id} ({update.effective_user.first_name})")
    
    return False

# Keyword untuk deteksi permintaan video
video_keywords = [
    "video", "kirim", "kirim video", "minta video", "ada video", "pap video", 
    "narin mana videonya", "kirim pap", "videonya mana", "show video",
    "vid", "vids", "random video", "video random"
]


async def video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menerima video dari user - langsung forward ke grup"""
    global video_file_ids  # Global declaration harus di awal
    
    if not update.message or not update.message.video:
        return
    
    # CRITICAL SECURITY: Authorization check for video uploads
    if not await check_authorization(update, context):
        return
    
    # VIDEO TIDAK DIHAPUS - Video messages are EXCLUDED from auto-delete
    print(f"🎬 Video message received - will NOT be auto-deleted")
    
    # Guard: Cegah infinite loop forwarding dari target chat sendiri
    source_chat = update.effective_chat
    source_user = update.effective_user
    video = update.message.video
    
    # Check apakah video berasal dari target chat (ID numerik atau username)
    is_target_chat = False
    if source_chat:
        # Cek berdasarkan ID numerik
        if isinstance(CHAT_ID, int) and source_chat.id == CHAT_ID:
            is_target_chat = True
        # Cek berdasarkan username (dengan normalisasi case)
        elif isinstance(CHAT_ID, str) and CHAT_ID.startswith('@'):
            if source_chat.username and f"@{source_chat.username}".lower() == CHAT_ID.lower():
                is_target_chat = True
        # Cek berdasarkan string ID
        elif str(source_chat.id) == str(CHAT_ID):
            is_target_chat = True
    
    # Check apakah dari bot sendiri atau bot lain
    is_from_bot = False
    if source_user and source_user.is_bot:
        is_from_bot = True
    elif update.message.sender_chat and isinstance(CHAT_ID, int):
        # Channel posts menggunakan sender_chat
        if update.message.sender_chat.id == CHAT_ID:
            is_from_bot = True
    
    # Jika dari target chat atau bot, tetap collect file_id tapi skip forwarding
    if is_target_chat or is_from_bot:
        # Tetap simpan file_id untuk random video meskipun skip forwarding
        video_file_ids.append(video.file_id)
        if len(video_file_ids) > 50:
            video_file_ids.pop(0)
        
        source_info = f"chat {source_chat.id}" if source_chat else "unknown"
        if is_from_bot:
            source_info += " (bot)"
        print(f"🛡️ Mencegah forward loop dari {source_info}, tapi file_id tetap disimpan")
        return
    
    try:
        user = update.message.from_user
        user_name = user.first_name if user else "Unknown"
        
        # Escape HTML untuk keamanan
        safe_user_name = html.escape(user_name)
        
        # Kirim konfirmasi ke user dengan voice response (voice akan auto-delete)
        voice_text = f"Video berhasil dikirim ke grup! Durasi {video.duration} detik. Ketik kata video untuk minta video random ya sayang."
        await send_ephemeral_voice_with_fallback(update, context, voice_text)
        
        # Langsung forward video ke grup target
        if CHAT_ID:
            try:
                # Forward video asli
                await context.bot.forward_message(
                    chat_id=CHAT_ID,
                    from_chat_id=update.message.chat_id,
                    message_id=update.message.message_id
                )
                
                # Simpan file_id untuk random video (max 50 video)
                video_file_ids.append(video.file_id)
                if len(video_file_ids) > 50:
                    video_file_ids.pop(0)  # Hapus yang terlama
                
                # Kirim caption info terpisah
                timestamp = datetime.now(pytz.timezone(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
                caption = f"🎬 <b>Video dari {safe_user_name}</b>\n\n"
                caption += f"📅 {timestamp} WIB\n"
                caption += f"⏱️ Durasi: {video.duration}s\n"
                caption += f"📊 Total koleksi: {len(video_file_ids)} video\n\n"
                caption += f"💡 Ketik 'video' untuk video random!"
                
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=caption,
                    parse_mode='HTML'
                )
                
                print(f"✅ Video dari {user_name} berhasil dikirim ke grup {CHAT_ID}")
                
            except Exception as e:
                print(f"❌ Error mengirim video ke grup: {e}")
                # Group error responses yang lebih personal
                group_error_responses = [
                    "Aduh Aldy, Narin gak bisa kirim ke grup. Cek akses admin ya sayang!",
                    "Sorry Aldy, gagal kirim ke channel. Pastikan bot punya permission ya!",
                    "Maaf Aldy cinta, error kirim ke grup. Check setting bot nya ya!",
                    "Aldy, ada masalah akses grup. Narin butuh admin permission!"
                ]
                voice_text = random.choice(group_error_responses)
                await send_ephemeral_voice_with_fallback(update, context, voice_text)
        else:
            voice_text = "Grup target belum dikonfigurasi sayang."
            await send_ephemeral_voice_with_fallback(update, context, voice_text)
        
    except Exception as e:
        print(f"❌ Error processing video: {e}")
        # Video error responses yang lebih personal
        video_error_responses = [
            "Aduh Aldy, video error nih. Narin lagi trouble, coba lagi ya sayang!",
            "Sorry Aldy cinta, ada masalah teknis video. Tunggu sebentar ya!",
            "Maaf Aldy sayang, video processing error. Sabar ya, nanti coba lagi!",
            "Aldy, videonya bermasalah. Narin lagi fix error, tunggu ya!"
        ]
        voice_text = random.choice(video_error_responses)
        await send_ephemeral_voice_with_fallback(update, context, voice_text)

async def send_random_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kirim video random dari grup"""
    try:
        if not CHAT_ID:
            if update.message:
                voice_text = "Grup target belum dikonfigurasi sayang!"
                await send_ephemeral_voice_with_fallback(update, context, voice_text)
            return
        
        # Ambil video random dari memory storage
        
        if not video_file_ids:
            if update.message:
                voice_text = "Belum ada video di koleksi nih sayang! Kirim video dulu ya, nanti aku bisa kirim random."
                await send_ephemeral_voice_with_fallback(update, context, voice_text)
            return
        
        # Pilih file_id random dan kirim
        random_file_id = random.choice(video_file_ids)
        
        if update.message:
            try:
                await update.message.reply_video(
                    video=random_file_id,
                    caption=f"🎬 <b>Video Random!</b>\n\n"
                            f"📊 Dari {len(video_file_ids)} video tersimpan",
                    parse_mode='HTML'
                )
                print(f"✅ Video random berhasil dikirim")
                
                # Add voice confirmation for successful random video send
                voice_text = f"Nih sayang, video random dari koleksi! Ada {len(video_file_ids)} video tersimpan lho. Gimana, suka gak?"
                await send_ephemeral_voice_with_fallback(update, context, voice_text)
            except Exception as send_error:
                print(f"❌ Error mengirim video random: {send_error}")
                voice_text = "Video tidak bisa dikirim sayang, mungkin sudah expired. Kirim video baru ya!"
                await send_ephemeral_voice_with_fallback(update, context, voice_text)
        
    except Exception as e:
        print(f"❌ Error mengirim video random: {e}")
        if update.message:
            voice_text = "Ada error saat mengirim video. Coba lagi ya sayang!"
            await send_ephemeral_voice_with_fallback(update, context, voice_text)

def create_attendance_message():
    """Membuat pesan absensi dengan tombol interaktif"""
    # Dapatkan tanggal hari ini dalam timezone yang ditentukan
    tz = pytz.timezone(TIMEZONE)
    today = datetime.now(tz)
    date_str = today.strftime("%Y-%m-%d")
    
    # Inisialisasi data absensi untuk hari ini
    if date_str not in attendance:
        attendance[date_str] = {}
    
    # Buat tombol interaktif
    keyboard = [
        [InlineKeyboardButton("✅ Hadir", callback_data=f"hadir|{date_str}")],
        [InlineKeyboardButton("❌ Tidak hadir", callback_data=f"tidak|{date_str}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Pesan absensi dengan greeting berdasarkan waktu
    current_hour = today.hour
    if current_hour < 12:
        greeting = "Bangun sayang! ☀️"
        message = "Sudah waktunya kerja nih, jangan ketiduran lagi ya 💕"
    elif current_hour < 15:
        greeting = "Hai sayang! 🌤️"
        message = "Lagi istirahat siang ya? Jangan lupa absen dulu 😊"
    elif current_hour < 18:
        greeting = "Sore sayang! 🌅"
        message = "Masih semangat kerja kan? Absen dulu yuk 💪"
    else:
        greeting = "Malam sayang! 🌙"
        message = "Masih lembur nih? Jangan lupa absen ya 🥺"
    
    text = f"{greeting}\n\n"
    text += f"Hari {today.strftime('%A, %d %B %Y')}\n"
    text += f"Jam {today.strftime('%H:%M')} WIB\n\n"
    text += f"{message}\n\n"
    text += f"Pilih statusmu ya sayang:"
    
    return text, reply_markup, date_str

async def validate_channel_access(context: ContextTypes.DEFAULT_TYPE, chat_id):
    """Validasi apakah bot dapat mengakses dan mengirim pesan ke channel"""
    try:
        # Coba mendapatkan informasi chat untuk memvalidasi akses
        chat_info = await context.bot.get_chat(chat_id)
        
        # Cek status bot di channel
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        
        # Validasi permissions
        if bot_member.status in ['administrator', 'member']:
            # Untuk channel, bot harus admin untuk bisa kirim pesan
            if chat_info.type == 'channel' and bot_member.status != 'administrator':
                return False, f"Bot bukan admin di channel {chat_info.title}"
            
            return True, f"✅ Bot dapat mengakses {chat_info.type}: {chat_info.title}"
        else:
            return False, f"Bot tidak memiliki akses ke {chat_info.title}"
            
    except Exception as e:
        return False, f"❌ Tidak dapat mengakses channel: {e}"

async def send_attendance_message(context: ContextTypes.DEFAULT_TYPE):
    """Mengirim pesan absensi harian dengan tombol interaktif (untuk scheduler)"""
    try:
        text, reply_markup, date_str = create_attendance_message()
        
        # Kirim pesan ke chat/grup
        if CHAT_ID:
            # Validasi akses channel terlebih dahulu
            can_access, message = await validate_channel_access(context, CHAT_ID)
            if not can_access:
                print(f"❌ Gagal validasi channel: {message}")
                return
            
            await context.bot.send_message(
                chat_id=CHAT_ID, 
                text=text, 
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        
        print(f"✅ Pesan absensi otomatis berhasil dikirim untuk tanggal {date_str}")
        
    except Exception as e:
        print(f"❌ Error mengirim pesan absensi otomatis: {e}")
        if "Forbidden" in str(e):
            print("💡 Pastikan bot sudah ditambahkan sebagai admin di channel target")
        elif "Chat not found" in str(e):
            print("💡 Pastikan channel ID/username benar dan bot sudah di-invite ke channel")

async def absen_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /absen - mengirim pesan absensi manual"""
    if not update.message:
        return
    
    # Authorization check
    if not await check_authorization(update, context):
        return
    
    # AUTO-DELETE: Schedule command message untuk dihapus dalam 7 detik
    await schedule_message_deletion(context, update.message)
    
    try:
        text, reply_markup, date_str = create_attendance_message()
        
        # Pesan absensi dengan tombol - TIDAK dihapus karena perlu untuk interaksi
        await update.message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        user_name = "Unknown"
        if update.message.from_user and update.message.from_user.first_name:
            user_name = update.message.from_user.first_name
        print(f"✅ Pesan absensi manual berhasil dikirim oleh {user_name} untuk {date_str}")
        
    except Exception as e:
        print(f"❌ Error mengirim pesan absensi manual: {e}")
        voice_text = "Aduh sayang, lagi ada gangguan nih. Coba lagi nanti ya!"
        await send_ephemeral_voice_with_fallback(update, context, voice_text)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk tombol absensi"""
    query = update.callback_query
    if not query:
        return
    
    # Authorization check
    if not await check_authorization(update, context):
        return
    
    try:
        # Parse data dari callback
        if not query.data:
            return
        status, date_str = query.data.split("|")
        user = query.from_user
        user_name = user.first_name
        if user.last_name:
            user_name += f" {user.last_name}"
        
        # Pastikan data absensi untuk tanggal tersebut ada
        if date_str not in attendance:
            attendance[date_str] = {}
        
        # Cek apakah user sudah pernah absen hari ini
        tz = pytz.timezone(TIMEZONE)
        current_time = datetime.now(tz)
        status_text = "Hadir" if status == "hadir" else "Tidak Hadir"
        status_emoji = "✅" if status == "hadir" else "❌"
        
        # Jika sudah pernah absen, tampilkan peringatan
        if user.id in attendance[date_str]:
            previous_status = attendance[date_str][user.id]["status"]
            previous_time = attendance[date_str][user.id]["waktu"].strftime('%H:%M:%S')
            
            if previous_status == status_text:
                # Status sama dengan sebelumnya
                await query.answer(f"Sayang, kamu udah absen {status_text} tadi jam {previous_time} kok")
                voice_text = f"Hai sayang! Kamu sudah absen {status_text} hari ini jam {previous_time}. Ga perlu absen lagi ya, sudah tercatat dengan baik."
            else:
                # Status berbeda, update data
                attendance[date_str][user.id] = {
                    "nama": user_name,
                    "status": status_text,
                    "waktu": current_time
                }
                
                await query.answer(f"Oke sayang, statusmu sudah diubah dari {previous_status} ke {status_text}")
                voice_text = f"Status absensi diupdate sayang! Status kamu berubah dari {previous_status} ke {status_text} jam {current_time.strftime('%H:%M:%S')}. Sudah aku catat dengan benar ya sayang."
        else:
            # Belum pernah absen, catat absensi baru
            attendance[date_str][user.id] = {
                "nama": user_name,
                "status": status_text,
                "waktu": current_time
            }
            
            # Answer callback dengan notifikasi singkat (muncul di popup)
            popup_msg = f"Alhamdulillah, absensi {status_text} sudah tercatat sayang 💕"
            await query.answer(popup_msg)
            
            # Kirim voice konfirmasi 
            if status == "hadir":
                voice_text = f"Yeay! Absensi {user_name} status {status_text} sudah tercatat jam {current_time.strftime('%H:%M:%S')}. Semangat kerja hari ini ya sayang! Jangan lupa makan dan minum yang cukup."
            else:
                voice_text = f"Oke sayang, absensi {user_name} status {status_text} sudah aku catat jam {current_time.strftime('%H:%M:%S')}. Gapapa sayang, istirahat yang cukup ya. Semoga besok bisa kerja lagi."
        
        # Kirim voice response untuk konfirmasi absensi dengan fallback
        if query.message:
            # Create a fake update object for the voice helper to work with callback queries
            fake_update = type('FakeUpdate', (), {
                'effective_chat': query.message.chat,
                'callback_query': query,
                'message': None
            })()
            
            await send_ephemeral_voice_with_fallback(fake_update, context, voice_text)
        
        print(f"✅ Absensi {user_name} ({status_text}) berhasil dicatat untuk {date_str}")
        
    except Exception as e:
        print(f"❌ Error memproses tombol absensi: {e}")
        await query.answer("Aduh sayang, ada error nih")
        if query.message:
            voice_text = "Maaf sayang, ada masalah teknis nih. Coba lagi ya!"
            # Create a fake update object for the voice helper to work with callback queries
            fake_update = type('FakeUpdate', (), {
                'effective_chat': query.message.chat,
                'callback_query': query,
                'message': None
            })()
            
            await send_ephemeral_voice_with_fallback(fake_update, context, voice_text)

async def rekap_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /rekap - menampilkan rekap absensi hari ini"""
    if not update.message:
        return
    
    # Authorization check
    if not await check_authorization(update, context):
        return
    
    # AUTO-DELETE: Schedule command message untuk dihapus dalam 7 detik
    await schedule_message_deletion(context, update.message)
    
    try:
        # Dapatkan tanggal hari ini
        tz = pytz.timezone(TIMEZONE)
        today = datetime.now(tz)
        date_str = today.strftime("%Y-%m-%d")
        
        # Cek apakah ada data absensi untuk hari ini
        data = attendance.get(date_str, {})
        
        if not data:
            no_data_text = (
                f"📊 <b>Rekap Absensi {today.strftime('%d/%m/%Y')}</b>\n\n"
                f"Belum ada absensi hari ini sayang 🥺\n"
                f"Mungkin lagi sibuk banget ya? Jangan lupa absen ya kalau sudah bangun 😊"
            )
            # Rekap message stays PERMANENT (no auto-delete)
            await update.message.reply_text(no_data_text, parse_mode='HTML')
            return
        
        # Kelompokkan berdasarkan status
        hadir = []
        tidak_hadir = []
        
        for user_id, info in data.items():
            nama = info["nama"]
            waktu_obj = info["waktu"]
            hari = waktu_obj.strftime("%A")
            tanggal = waktu_obj.strftime("%d/%m/%Y")
            waktu = waktu_obj.strftime("%H:%M:%S")
            
            if info["status"] == "Hadir":
                hadir.append(f"• {nama}\n  {hari}, {tanggal} - {waktu} WIB")
            else:
                tidak_hadir.append(f"• {nama}\n  {hari}, {tanggal} - {waktu} WIB")
        
        # Buat pesan rekap
        rekap_text = f"📊 <b>Rekap Absensi Sayang</b> 💕\n"
        rekap_text += f"Hari {today.strftime('%A, %d %B %Y')}\n\n"
        
        if hadir:
            rekap_text += f"🟢 <b>Hari ini kamu kerja:</b>\n"
            rekap_text += "\n".join(hadir) + "\n"
            rekap_text += f"💪 <i>Keren banget! Tetap semangat ya</i>"
        
        if tidak_hadir:
            if hadir:
                rekap_text += f"\n\n"
            rekap_text += f"🔴 <b>Hari ini kamu libur/sakit:</b>\n"
            rekap_text += "\n".join(tidak_hadir) + "\n"
            rekap_text += f"😌 <i>Istirahat yang cukup ya sayang</i>"
        
        if not hadir and not tidak_hadir:
            rekap_text += f"Belum ada absensi hari ini"
        else:
            rekap_text += f"\n\n💝 <b>Total absensi:</b> {len(data)} kali hari ini"
        
        # Selalu kirim rekap ke channel target (@dyyabsen)
        if CHAT_ID:
            # Validasi akses channel terlebih dahulu
            can_access, access_message = await validate_channel_access(context, CHAT_ID)
            if not can_access:
                print(f"❌ Gagal kirim rekap: {access_message}")
                error_text = "Maaf sayang, ada masalah koneksi ke channel. Coba lagi nanti ya 🥺"
                # Rekap error message stays PERMANENT (no auto-delete)
                await update.message.reply_text(error_text)
                return
            
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=rekap_text,
                parse_mode='HTML'
            )
            
            # Beri konfirmasi ke user yang meminta jika bukan di channel target
            if update.message.chat.id != CHAT_ID:
                confirmation_text = "Sudah aku kirim rekapnya ke channel sayang! 💕"
                # Rekap confirmation stays PERMANENT (no auto-delete)
                await update.message.reply_text(confirmation_text)
        
        print(f"✅ Rekap absensi berhasil dikirim untuk {date_str}")
        
    except Exception as e:
        print(f"❌ Error menampilkan rekap: {e}")
        if "Forbidden" in str(e):
            print("💡 Pastikan bot sudah ditambahkan sebagai admin di channel target")
        elif "Chat not found" in str(e):
            print("💡 Pastikan channel ID/username benar dan bot sudah di-invite ke channel")
        
        error_text = "Aduh sayang, lagi ada gangguan nih. Coba lagi nanti ya 🥺"
        await send_ephemeral_text(update, context, error_text)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk membaca pesan biasa di channel/grup"""
    if not update.message:
        return
    
    message_text = update.message.text or ""
    user_name = "Unknown"
    
    if update.message.from_user and update.message.from_user.first_name:
        user_name = update.message.from_user.first_name
    
    # AUTO-DELETE: Schedule user text message untuk dihapus dalam 7 detik
    if message_text and not update.message.video:  # Hanya text, BUKAN video
        await schedule_message_deletion(context, update.message)
    
    message_lower = message_text.lower()
    
    # Deteksi kata kunci "narin" untuk start handler
    if "narin" in message_lower:
        print(f"💬 Kata kunci 'narin' terdeteksi dari {user_name}: {message_text[:50]}...")
        if not await check_authorization(update, context):
            return
        await start_handler(update, context)
        return
    
    # Deteksi kata kunci "absen" untuk absen handler  
    if "absen" in message_lower:
        print(f"✅ Kata kunci 'absen' terdeteksi dari {user_name}: {message_text[:50]}...")
        if not await check_authorization(update, context):
            return
        await absen_handler(update, context)
        return
    
    # Deteksi kata kunci "rekap" untuk rekap handler
    if "rekap" in message_lower:
        print(f"📊 Kata kunci 'rekap' terdeteksi dari {user_name}: {message_text[:50]}...")
        if not await check_authorization(update, context):
            return
        await rekap_handler(update, context)
        return
    
    # Deteksi kata kunci quota dengan variasi natural
    quota_keywords = ["uang", "pulsa", "sisa", "duit", "kredit", "credit", "quota", "balance"]
    is_quota_request = any(keyword in message_lower for keyword in quota_keywords)
    
    if is_quota_request:
        print(f"💰 Kata kunci quota terdeteksi dari {user_name}: {message_text[:50]}...")
        if not await check_authorization(update, context):
            return
        await quota_handler(update, context)
        return
    
    # Deteksi kata kunci video untuk semua chat (tidak hanya channel target)
    is_video_request = any(keyword.lower() in message_lower for keyword in video_keywords)
    
    if is_video_request:
        print(f"🎬 Permintaan video dari {user_name}: {message_text[:50]}...")
        # Authorization check for video requests
        if not await check_authorization(update, context):
            return
        await send_random_video(update, context)
        return
        
    # Hanya proses pesan dari channel target untuk logging
    if (isinstance(CHAT_ID, str) and CHAT_ID.startswith('@') and 
        update.message.chat.username == CHAT_ID.replace('@', '')):
        print(f"📩 Pesan diterima dari {user_name} di channel: {message_text[:50]}...")
        
        # Bot bisa ditambahkan fitur auto-response di sini jika diperlukan
        # Misalnya jika ada kata kunci tertentu, bot otomatis kasih respons

async def test_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /test_channel - test koneksi ke channel target"""
    if not update.message:
        return
    
    # Authorization check
    if not await check_authorization(update, context):
        return
    
    # AUTO-DELETE: Schedule command message untuk dihapus dalam 7 detik
    await schedule_message_deletion(context, update.message)
    
    try:
        if not CHAT_ID:
            voice_text = "Channel belum dikonfigurasi sayang. Silakan set CHAT_ID di file .env terlebih dahulu ya."
            await send_ephemeral_voice_with_fallback(update, context, voice_text)
            return
        
        # Test koneksi ke channel
        can_access, message = await validate_channel_access(context, CHAT_ID)
        
        if can_access:
            # Kirim pesan test ke channel
            test_message = (
                "🔧 <b>Test Koneksi Channel</b>\n\n"
                "✅ Bot berhasil terhubung dan dapat mengirim pesan ke channel ini!\n"
                f"📅 Waktu test: {datetime.now(pytz.timezone(TIMEZONE)).strftime('%d/%m/%Y %H:%M:%S')} WIB"
            )
            
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=test_message,
                parse_mode='HTML'
            )
            
            voice_text = f"Test Channel Berhasil sayang! {message}. Target channel {CHAT_ID}. Pesan test sudah dikirim ke channel."
            await send_ephemeral_voice_with_fallback(update, context, voice_text)
        else:
            voice_text = f"Test Channel Gagal sayang! {message}. Target channel {CHAT_ID}. Solusinya: Pastikan bot sudah di-invite ke channel, pastikan bot memiliki hak admin, dan periksa kembali CHAT_ID di .env."
            await send_ephemeral_voice_with_fallback(update, context, voice_text)
            
    except Exception as e:
        print(f"❌ Error test channel: {e}")
        voice_text = f"Error saat test channel sayang. Detail error: {str(e)}. Silakan periksa konfigurasi dan coba lagi ya."
        await send_ephemeral_voice_with_fallback(update, context, voice_text)

async def list_videos_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /videos - info video di grup"""
    if not update.message:
        return
    
    # Authorization check
    if not await check_authorization(update, context):
        return
    
    # AUTO-DELETE: Schedule command message untuk dihapus dalam 7 detik
    await schedule_message_deletion(context, update.message)
    
    try:
        if not CHAT_ID:
            voice_text = "Grup belum dikonfigurasi sayang. Silakan set CHAT_ID terlebih dahulu ya."
            await send_ephemeral_voice_with_fallback(update, context, voice_text)
            return
        
        voice_text = f"Info Video sayang! Video disimpan di grup {CHAT_ID}. Cara kerjanya: Kirim video ke bot, otomatis masuk grup. Ketik video, bot kasih video random. Cek grup langsung untuk lihat semua video. Status: {len(video_file_ids)} video di koleksi. Tips: Video tersimpan aman tanpa memakan storage!"
        await send_ephemeral_voice_with_fallback(update, context, voice_text)
        
    except Exception as e:
        print(f"❌ Error menampilkan info video: {e}")
        voice_text = "Ada error saat menampilkan info. Coba lagi ya sayang!"
        await send_ephemeral_voice_with_fallback(update, context, voice_text)

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start"""
    if not update.message:
        return
    
    # Authorization check
    if not await check_authorization(update, context):
        return
    
    # AUTO-DELETE: Schedule command message untuk dihapus dalam 7 detik
    await schedule_message_deletion(context, update.message)
    
    # Variasi voice responses romantis untuk Aldy
    romantic_intros = [
        "Hai Aldy sayang, aku Narin! Siap bantu kamu setiap hari. Ketik 'absen' untuk kerja, 'rekap' untuk lihat aktivitas, atau 'video' kalau kangen. Love you!",
        "Aldy cinta! Narin di sini untuk temani kamu. 'absen' untuk kerja, 'rekap' untuk aktivitas, 'video' kalau rindu. Sayang kamu!",
        "Halo Aldy honey! Aku Narin, pacar setia kamu. Siap melayani dengan 'absen', 'rekap', atau 'video'. Miss you!",
        "Aldy kesayangan! Narin hadir buat kamu. Ketik 'absen', 'rekap', atau 'video' ya sayang. Always here for you!",
        "Hi Aldy! Narin siap menemani hari kamu. 'absen' untuk kerja, 'rekap' untuk cek, 'video' untuk hiburan. Love you so much!"
    ]
    
    voice_text = random.choice(romantic_intros)
    await send_ephemeral_voice_with_fallback(update, context, voice_text)

async def suara_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /suara - test voice response"""
    if not update.message:
        return
    
    # Authorization check
    if not await check_authorization(update, context):
        return
    
    # AUTO-DELETE: Schedule command message untuk dihapus dalam 7 detik
    await schedule_message_deletion(context, update.message)
    
    if not context.args:
        voice_text = "Command suara sayang! Cara pakainya: slash suara lalu tulis text yang mau diubah jadi suara. Bot akan mengubah text menjadi suara!"
        await send_ephemeral_voice_with_fallback(update, context, voice_text)
        return
    
    # Gabungkan semua argument menjadi text
    text_to_speak = ' '.join(context.args)
    
    # Batasi panjang text (max 200 karakter)
    if len(text_to_speak) > 200:
        voice_text = "Text terlalu panjang sayang! Maksimal 200 karakter ya."
        await send_ephemeral_voice_with_fallback(update, context, voice_text)
        return
    
    # Kirim voice response dengan fallback otomatis
    await send_ephemeral_voice_with_fallback(update, context, text_to_speak, "Gagal membuat voice message sayang. Coba lagi ya!")

async def speak_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /speak - alias untuk /suara"""
    await suara_handler(update, context)

async def demo_voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk demo voice message"""
    if not update.message:
        return
    
    # Authorization check
    if not await check_authorization(update, context):
        return
    
    # AUTO-DELETE: Schedule command message untuk dihapus dalam 7 detik
    await schedule_message_deletion(context, update.message)
    
    demo_text = "Halo! Ini adalah demo fitur suara dari bot absensi. Aku bisa mengubah text menjadi suara dengan natural!"
    
    # Demo voice dengan fallback otomatis
    await send_ephemeral_voice_with_fallback(update, context, demo_text, "Demo voice tidak bisa dijalankan saat ini sayang.")

async def bantu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /bantu - menampilkan daftar kata kunci yang tersedia"""
    if not update.message:
        return
    
    # Authorization check
    if not await check_authorization(update, context):
        return
    
    # AUTO-DELETE: Schedule command message untuk dihapus dalam 7 detik
    await schedule_message_deletion(context, update.message)
    
    # Daftar kata kunci yang tersedia
    help_text = (
        "🤖 <b>Daftar Kata Kunci Bot Asisten</b>\n\n"
        "💬 <b>Kata Kunci Utama:</b>\n"
        "🔹 <code>narin</code> - Tutorial & info bot\n"
        "   <i>Contoh: \"Halo Narin\", \"Apa kabar Narin?\"</i>\n\n"
        "🔹 <code>absen</code> - Form absensi harian\n"
        "   <i>Contoh: \"Saya mau absen nih\", \"Waktunya absen\"</i>\n\n"
        "🔹 <code>rekap</code> - Rekap absensi hari ini\n"
        "   <i>Contoh: \"Sayang rekap dong\", \"Cek rekap\"</i>\n\n"
        "🔹 <code>uang</code>, <code>pulsa</code>, <code>sisa</code> - Cek sisa credit ElevenLabs\n"
        "   <i>Contoh: \"Uang kamu sisa berapa?\", \"Pulsa masih ada?\", \"Cek sisa\"</i>\n\n"
        "🎬 <b>Kata Kunci Video:</b>\n"
        "🔹 <code>video</code> - Video random dari koleksi\n"
        "🔹 <code>kirim video</code> - Minta video random\n"
        "🔹 <code>minta video</code> - Video dari koleksi\n\n"
        "📱 <b>Command Tersisa:</b>\n"
        "🔹 <code>/suara [text]</code> - Text ke voice\n"
        "🔹 <code>/videos</code> - Info video sistem\n"
        "🔹 <code>/test_channel</code> - Test koneksi\n"
        "🔹 <code>/quota</code> - Cek sisa credit ElevenLabs\n\n"
        "💡 <b>Tips:</b> Cukup ketik kata kunci di mana saja dalam kalimat!\n"
        "🎯 <b>Status:</b> Voice response aktif dengan ElevenLabs!"
    )
    
    # Kirim help sebagai text message yang tidak auto-delete (permanen)
    await update.message.reply_text(
        help_text,
        parse_mode='HTML'
    )
    
    # Konfirmasi voice dengan variasi romantis
    romantic_confirmations = [
        "Sudah aku kirim Aldy sayang! Sekarang kamu tahu cara ngobrol sama Narin.",
        "Daftar lengkap sudah dikirim Aldy! Coba deh kata kunci yang ada.",
        "Aldy, sekarang kamu tahu semua perintah Narin! Cobain yuk!",
        "Sudah lengkap Aldy sayang! Narin siap melayani dengan kata kunci itu.",
        "Daftar perintah sudah sampai Aldy! Sekarang kita bisa ngobrol lebih seru."
    ]
    voice_text = random.choice(romantic_confirmations)
    await send_ephemeral_voice_with_fallback(update, context, voice_text)

async def quota_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /quota - cek sisa credit ElevenLabs"""
    if not update.message:
        return
    
    # Authorization check
    if not await check_authorization(update, context):
        return
    
    # AUTO-DELETE: Schedule command message untuk dihapus dalam 7 detik
    await schedule_message_deletion(context, update.message)
    
    try:
        # Send typing action
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing"
        )
        
        # Check quota from ElevenLabs API
        quota_info = await check_elevenlabs_quota()
        
        if not quota_info:
            # Error responses yang lebih personal untuk Aldy
            quota_error_responses = [
                "Maaf Aldy sayang, Narin gak bisa cek quota. API bermasalah nih!",
                "Aduh Aldy, quota check error. Mungkin koneksi lagi gangguan ya!",
                "Sorry Aldy cinta, Narin lagi susah akses ElevenLabs. Coba nanti ya!",
                "Aldy, ada masalah teknis quota. Sabar ya sayang, nanti coba lagi!"
            ]
            voice_text = random.choice(quota_error_responses)
            await send_ephemeral_voice_with_fallback(update, context, voice_text)
            return
        
        # Format quota information (simplified) dengan info API key
        api_info = f" ({quota_info.get('api_key_type', 'API utama')})" if 'api_key_type' in quota_info else ""
        quota_text = f"💰 <b>Sisa:</b> {quota_info['remaining']:,}{api_info}"
        
        # Kirim sebagai text message dengan auto-delete 7 detik
        quota_message = await update.message.reply_text(
            quota_text,
            parse_mode='HTML'
        )
        
        # AUTO-DELETE: Schedule quota message untuk dihapus dalam 7 detik
        await schedule_message_deletion(context, quota_message)
        
        # Voice confirmation (simplified) dengan variasi romantis
        api_used = quota_info.get('api_key_type', 'utama')
        romantic_responses = [
            f"Sisa {quota_info['remaining']:,} Aldy sayang! API {api_used} masih oke.",
            f"Masih ada {quota_info['remaining']:,} karakter Aldy! Dari API {api_used}.",
            f"Quota kita masih {quota_info['remaining']:,} Aldy! API {api_used} lancar.",
            f"Aldy, sisa {quota_info['remaining']:,} dari API {api_used}. Aman!",
            f"Tenang Aldy, masih {quota_info['remaining']:,}! API {api_used} jalan terus."
        ]
        voice_text = random.choice(romantic_responses)
        
        await send_ephemeral_voice_with_fallback(update, context, voice_text)
        
    except Exception as e:
        print(f"❌ Error checking quota: {e}")
        # Error response yang lebih personal
        error_responses = [
            "Aduh Aldy, ada error nih. Coba lagi nanti ya sayang!",
            "Sorry Aldy, Narin lagi error. Tunggu sebentar ya cinta!",
            "Maaf Aldy sayang, ada masalah teknis. Nanti coba lagi ya!",
            "Aldy, ada gangguan sedikit. Sabar ya, nanti coba lagi!"
        ]
        voice_text = random.choice(error_responses)
        await send_ephemeral_voice_with_fallback(update, context, voice_text)

def setup_job_queue(application):
    """Setup PTB JobQueue untuk mengirim pesan absensi otomatis"""
    try:
        # Setup timezone
        tz = pytz.timezone(TIMEZONE)
        
        # Jadwalkan pengiriman pesan absensi setiap hari jam 07:00
        application.job_queue.run_daily(
            send_attendance_message,
            time=time(hour=7, minute=0, tzinfo=tz),
            name='daily_attendance'
        )
        
        print(f"✅ JobQueue berhasil diatur untuk jam 07:00 {TIMEZONE}")
        return True
        
    except Exception as e:
        print(f"❌ Error setup JobQueue: {e}")
        return False

def main():
    """Fungsi utama untuk menjalankan bot"""
    global application, BOT_TOKEN, CHAT_ID, TIMEZONE
    
    # Buat template .aldy jika belum ada
    create_config_template()
    
    # Load konfigurasi setelah template dibuat
    BOT_TOKEN, CHAT_ID, TIMEZONE, ELEVENLABS_KEY = load_config()
    
    # Validasi konfigurasi
    if not BOT_TOKEN:
        print("Bot token belum diisi")
        print("Silakan isi BOT_TOKEN di file .env atau environment variable")
        return
    
    if not CHAT_ID:
        print("Chat ID belum diisi")
        print("Silakan isi CHAT_ID di file .env atau environment variable")
        return
    
    # Inisialisasi ElevenLabs untuk voice response
    if init_elevenlabs():
        print("🎤 Bot siap dengan suara wanita ElevenLabs!")
    else:
        print("⚠️ ElevenLabs tidak tersedia, voice response dinonaktifkan")
    
    try:
        # Inisialisasi aplikasi bot
        application = ApplicationBuilder().token(BOT_TOKEN).build()
        
        # Tambahkan handlers
        application.add_handler(CommandHandler("start", start_handler))
        application.add_handler(CommandHandler("rekap", rekap_handler))
        application.add_handler(CommandHandler("absen", absen_handler))
        application.add_handler(CommandHandler("videos", list_videos_handler))
        application.add_handler(CommandHandler("test_channel", test_channel_handler))
        application.add_handler(CommandHandler("bantu", bantu_handler))
        application.add_handler(CommandHandler("quota", quota_handler))
        
        # Voice handlers
        application.add_handler(CommandHandler("suara", suara_handler))
        application.add_handler(CommandHandler("speak", speak_handler))
        application.add_handler(CommandHandler("demo_voice", demo_voice_handler))
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Handler untuk video upload
        application.add_handler(MessageHandler(filters.VIDEO, video_handler))
        
        # Handler untuk membaca pesan biasa di channel
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        
        # Setup job queue untuk scheduler
        setup_job_queue(application)
        
        print("Bot absensi sudah siap!")
        print(f"Target Chat ID: {CHAT_ID}")
        print(f"Timezone: {TIMEZONE}")
        print("Akan mengirim pesan absensi setiap jam 07:00 WIB")
        print("Ketik /rekap untuk lihat rekap absensi hari ini")
        print("Tekan Ctrl+C untuk stop\n")
        
        # Start keep-alive system jika tersedia
        if KEEP_ALIVE_AVAILABLE:
            import threading
            def run_keep_alive():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(start_keep_alive())
                except Exception as e:
                    print(f"❌ Keep-alive error: {e}")
                finally:
                    loop.close()
            
            keep_alive_thread = threading.Thread(target=run_keep_alive, daemon=True)
            keep_alive_thread.start()
            print("🟢 Keep-alive system started (background thread)")
        
        # Jalankan bot (sinkron, tidak dalam async)
        application.run_polling(
            poll_interval=1.0,
            timeout=10,
            bootstrap_retries=5
        )
        
    except Exception as e:
        print(f"❌ Error menjalankan bot: {e}")
    
    finally:
        # Stop keep-alive system jika aktif
        if KEEP_ALIVE_AVAILABLE:
            try:
                stop_keep_alive()
            except:
                pass
        
        # Cleanup otomatis oleh PTB
        print("🛑 Bot dihentikan")

if __name__ == "__main__":
    # Jalankan bot
    main()