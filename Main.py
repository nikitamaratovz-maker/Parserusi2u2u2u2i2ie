# -*- coding: utf-8 -*-
import re
import time
import random
import datetime
import sqlite3
import threading
import logging
import os
import requests
from collections import defaultdict
from telebot import types
import telebot
from telethon import TelegramClient
import asyncio
from telethon.errors import FloodWaitError, PhoneNumberInvalidError, SessionPasswordNeededError, PhoneCodeInvalidError, RPCError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import InputPeerChannel, Channel, User
from telethon.tl.functions.account import UpdateStatusRequest
from telethon import errors

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TOKEN = '8289373453:AAEcMeZuN9RzPA8Bcg129BBA15CFUJ9JM6A'
bot = telebot.TeleBot(TOKEN)
bot.skip_pending = True

ADMIN_ID = 8727723180
YOUR_USERNAME = "@ubmuh"
REQUIRED_CHANNEL = "@krectbII"
CHANNEL_LINK = "https://t.me/krectbII"
SELLER_USERNAME = "@ubmuh"

API_ID = 34928216
API_HASH = "29f66350a892e8b69a83b50d7e99bd27"

vowels = 'aeiouy'
consonants = 'bcdfghklmnprstvw'
all_letters = 'abcdefghijklmnopqrstuvwxyz'
BASE_SEARCHES = 5
SEARCH_ATTEMPTS = 60
FILTER_ATTEMPTS = 60
REQUEST_TIMEOUT = 0.1

patterns_5 = ['CVCVC', 'VCVCV', 'CVCCV', 'VCCVC', 'CCVCC', 'CVVCC']
patterns_6 = ['CVCVCV', 'VCVCVC', 'CVCCVC', 'VCCVCC', 'CVCVCC', 'CVVCVC']

PREMIUM_PRICES = {1: 50, 3: 120, 7: 210, 30: 400}
REFERRAL_REWARDS = {5: 1, 10: 2, 15: 3, 20: 4}
CRYPTO_BOT_TOKEN = "559739:AALFf0i5EFhsnAiXQ2CCrKtWVf2MZFfMmTz"

EMOJI = {
    'search': '🔍', 'found': '✅', 'error': '❌', 'premium': '💎',
    'profile': '👤', 'stats': '📊', 'info': 'ℹ️', 'referral': '👥',
    'top': '🏆', 'trap': '🎯', 'filter': '🔎', 'channel': '📢',
    'admin': '⚙️', 'star': '⭐', 'crown': '👑', 'fire': '🔥',
    'rocket': '🚀', 'zap': '⚡', 'lock': '🔒', 'time': '⏱️',
    'ban': '🚫', 'unban': '✅'
}

conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
db_lock = threading.RLock()

user_actions = defaultdict(list)
blocked_users = {}
ACTION_COOLDOWN = 2
START_LIMIT = 3
START_WINDOW = 5
BLOCK_DURATION = 300

# Таблица для сессий
cursor.execute('''
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_name TEXT UNIQUE,
    phone TEXT,
    proxy TEXT,
    is_active INTEGER DEFAULT 1,
    added_at TEXT,
    last_check TEXT,
    status TEXT DEFAULT 'active'
)
''')
conn.commit()

# Глобальный словарь для хранения клиентов сессий
sessions_clients = {}
sessions_lock = threading.RLock()
loop = None

# Хранилище для временных данных сессии
temp_session_data = {}

# Список используемых клиентов для поиска
current_session_index = 0
available_clients = []

def migrate_database():
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    required_columns = {
        'trial_used': 'INTEGER DEFAULT 0',
        'search_packages': 'INTEGER DEFAULT 0',
        'banned': 'INTEGER DEFAULT 0'
    }
    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                conn.commit()
            except: pass

cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    referrer_id INTEGER,
    referrals_count INTEGER DEFAULT 0,
    subscription_end TEXT,
    searches_today INTEGER DEFAULT 0,
    last_search_date TEXT,
    created_date TEXT,
    total_searches INTEGER DEFAULT 0,
    found_count INTEGER DEFAULT 0,
    subscribed INTEGER DEFAULT 0,
    referral_activated INTEGER DEFAULT 0,
    trial_used INTEGER DEFAULT 0,
    search_packages INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS found (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    length INTEGER,
    price TEXT,
    found_date TEXT,
    finder_id INTEGER
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS traps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    target_username TEXT,
    status TEXT DEFAULT 'active',
    created_date TEXT
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS gifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER,
    receiver_id INTEGER,
    days INTEGER,
    payment_method TEXT,
    created_date TEXT
)''')

conn.commit()
migrate_database()

def get_user(user_id):
    with db_lock:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None

def create_user(user_id, username=None, referrer_id=None):
    with db_lock:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            return get_user(user_id), False
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('INSERT INTO users (user_id, username, referrer_id, created_date) VALUES (?, ?, ?, ?)',
                       (user_id, username, referrer_id, now))
        conn.commit()
        return get_user(user_id), True

def update_user(user_id, **kwargs):
    allowed_fields = {
        'username', 'referrer_id', 'referrals_count', 'subscription_end',
        'searches_today', 'last_search_date', 'total_searches',
        'found_count', 'subscribed', 'referral_activated', 'trial_used',
        'search_packages', 'banned'
    }
    with db_lock:
        for key, val in kwargs.items():
            if key in allowed_fields:
                cursor.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (val, user_id))
        conn.commit()

def add_session_to_db(session_name, phone, proxy=None):
    with db_lock:
        cursor.execute('''
        INSERT OR REPLACE INTO sessions (session_name, phone, proxy, added_at, status)
        VALUES (?, ?, ?, ?, 'active')
        ''', (session_name, phone, proxy, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()

def get_all_sessions():
    with db_lock:
        cursor.execute('SELECT id, session_name, phone, proxy, is_active, status FROM sessions ORDER BY id DESC')
        return cursor.fetchall()

def delete_session(session_id):
    with db_lock:
        cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
        conn.commit()

def update_session_status(session_name, status):
    with db_lock:
        cursor.execute('UPDATE sessions SET status = ?, last_check = ? WHERE session_name = ?',
                       (status, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session_name))
        conn.commit()

def get_active_sessions():
    with db_lock:
        cursor.execute('SELECT session_name, proxy FROM sessions WHERE status = "active"')
        return cursor.fetchall()

def refresh_available_clients():
    """Обновляет список доступных клиентов сессий для поиска"""
    global available_clients
    with sessions_lock:
        available_clients = list(sessions_clients.values())
    return len(available_clients)

def parse_http_proxy(proxy_str):
    """Парсит HTTP/HTTPS прокси в формат Telethon"""
    if not proxy_str or proxy_str.lower() == 'нет':
        return None
    try:
        proxy_type = None
        if proxy_str.startswith('http://'):
            proxy_str = proxy_str[7:]
            proxy_type = 'http'
        elif proxy_str.startswith('https://'):
            proxy_str = proxy_str[8:]
            proxy_type = 'http'
        elif proxy_str.startswith('socks5://'):
            proxy_str = proxy_str[9:]
            proxy_type = 'socks5'
        
        if '@' in proxy_str:
            auth_part, addr_part = proxy_str.split('@')
            if ':' in auth_part:
                username, password = auth_part.split(':', 1)
            else:
                username, password = auth_part, ''
            ip, port = addr_part.split(':')
        else:
            username, password = None, None
            ip, port = proxy_str.split(':')
        
        return {
            'proxy_type': proxy_type or 'socks5',
            'addr': ip,
            'port': int(port),
            'username': username,
            'password': password
        }
    except Exception as e:
        logger.error(f"Ошибка парсинга прокси {proxy_str}: {e}")
        return None

def check_rate_limit(user_id, action_type='general'):
    current_time = time.time()
    if user_id in blocked_users:
        if current_time < blocked_users[user_id]:
            return False, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Вы заблокированы!</b>"
        else:
            del blocked_users[user_id]
            user_actions[user_id] = []
    actions = user_actions[user_id]
    if action_type == 'start':
        actions[:] = [t for t in actions if current_time - t < START_WINDOW]
        if len(actions) >= START_LIMIT:
            blocked_users[user_id] = current_time + BLOCK_DURATION
            user_actions[user_id] = []
            return False, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Вы заблокированы на 5 минут!</b>"
        actions.append(current_time)
        return True, None
    else:
        actions[:] = [t for t in actions if current_time - t < ACTION_COOLDOWN]
        if actions and (current_time - actions[-1]) < ACTION_COOLDOWN:
            return False, f"<tg-emoji emoji-id='5134438483867206614'>⏱️</tg-emoji> <b>Подожди немного</b>"
        actions.append(current_time)
        return True, None

def is_banned(user_id):
    user = get_user(user_id)
    return user and user.get('banned', 0) == 1

def validate_username(username):
    if not username: return False, "Пустой username"
    username = username.strip().lower().replace('@', '')
    if len(username) < 5 or len(username) > 32: return False, "Username должен быть от 5 до 32 символов"
    if not re.match(r'^[a-z0-9_]+$', username): return False, "Только латиница, цифры и _"
    return True, username

def add_search_packages(user_id, amount):
    user = get_user(user_id)
    current = user.get('search_packages', 0) if user else 0
    update_user(user_id, search_packages=current + amount)

def create_gift(sender_id, receiver_id, days, payment_method):
    with db_lock:
        cursor.execute("INSERT INTO gifts (sender_id, receiver_id, days, payment_method, created_date) VALUES (?, ?, ?, ?, ?)",
                       (sender_id, receiver_id, days, payment_method, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()

def check_crypto_payment(invoice_id):
    try:
        response = requests.get("https://pay.crypt.bot/api/getInvoices",
                                headers={"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN},
                                params={"invoice_ids": invoice_id}, timeout=10)
        data = response.json()
        if data.get('ok') and data.get('result'):
            items = data['result'].get('items', [])
            if items and items[0].get('status') == 'paid':
                return True
    except: pass
    return False

def activate_referral(user_id):
    user = get_user(user_id)
    if not user or user['referral_activated']: return False
    referrer_id = user['referrer_id']
    if not referrer_id or referrer_id == user_id: return False
    with db_lock:
        cursor.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (referrer_id,))
        cursor.execute("UPDATE users SET referral_activated = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        cursor.execute("SELECT referrals_count FROM users WHERE user_id = ?", (referrer_id,))
        ref_count = cursor.fetchone()[0]
    check_referral_rewards(referrer_id, ref_count)
    try:
        bot.send_message(referrer_id, f"<tg-emoji emoji-id='4916105371858240403'>🔥</tg-emoji> По твоей ссылке зарегистрировался новый пользователь!\n\n<tg-emoji emoji-id='4916086774649848789'>👥</tg-emoji> Всего рефералов: {ref_count}")
    except: pass
    return True

def check_referral_rewards(user_id, ref_count):
    user = get_user(user_id)
    if not user: return
    for need_refs, days in sorted(REFERRAL_REWARDS.items()):
        if ref_count >= need_refs:
            add_premium(user_id, days, from_ref=True)

def estimate_price(username):
    name = username.lower()
    score = 0
    if len(name) == 5: score += 80
    elif len(name) == 6: score += 50
    elif len(name) <= 8: score += 30
    else: score += 10
    if name.isalpha(): score += 40
    common_words = ['star', 'king', 'god', 'fire', 'moon', 'sun', 'dark', 'light', 'ice', 'gold', 'rose', 
                   'blue', 'red', 'sky', 'wolf', 'lion', 'eagle', 'ghost', 'storm', 'night', 'lord', 'soul',
                   'love', 'life', 'time', 'fate', 'luck', 'myth', 'hero', 'legend', 'demon', 'angel', 'magic',
                   'dream', 'hope', 'fear', 'rain', 'cloud', 'stone', 'steel', 'iron', 'void', 'zero',
                   'nova', 'zen', 'pro', 'max', 'ultra', 'mega', 'super', 'boss', 'og', 'prime', 'elite']
    for word in common_words:
        if word in name: score += 25
    for c in set(name):
        if name.count(c) >= 3 and c.isalpha(): score -= 15
    vowel_count = sum(1 for c in name if c in 'aeiouy')
    if 1 <= vowel_count <= 3 and len(name) >= 5: score += 15
    premium_letters = sum(1 for c in name if c in 'xzqvjk')
    score += premium_letters * 8
    if score >= 150: return "250-500 ⭐"
    elif score >= 120: return "150-300 ⭐"
    elif score >= 90: return "100-200 ⭐"
    elif score >= 60: return "50-100 ⭐"
    elif score >= 40: return "25-75 ⭐"
    else: return "10-50 ⭐"

def check_telegram_fast(username):
    try:
        r = requests.get(f"https://t.me/{username}", headers={'User-Agent': 'TelegramBot'}, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            if 'tgme_page_title' in r.text[:500]: return False
            return True
        return True
    except: return None

# ========== УЛУЧШЕННАЯ ПРОВЕРКА ЧЕРЕЗ СЕССИИ (РОТАЦИЯ) ==========
def get_available_client():
    """Возвращает случайного клиента из активных сессий"""
    with sessions_lock:
        if available_clients:
            return random.choice(available_clients)
    return None

async def _check_username_via_session(client, username):
    """Асинхронная проверка через клиент"""
    try:
        entity = await client.get_entity(f"@{username}")
        if entity:
            return False
        return True
    except ValueError:
        return True
    except FloodWaitError as e:
        logger.warning(f"Flood wait {e.seconds}s, waiting...")
        time.sleep(e.seconds)
        return await _check_username_via_session(client, username)
    except Exception as e:
        logger.error(f"Ошибка проверки через сессию: {e}")
        return None

def check_username_via_session_sync(username):
    """Синхронная обёртка для проверки через сессии"""
    client = get_available_client()
    if not client:
        return None
    
    try:
        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_check_username_via_session(client, username), loop)
            return future.result(timeout=10)
    except Exception as e:
        logger.error(f"Ошибка при проверке {username}: {e}")
    
    return None

def check_username_full(username):
    """Улучшенная проверка с приоритетом сессий"""
    
    # 1. Сначала проверяем через сессии (если есть)
    session_result = check_username_via_session_sync(username)
    if session_result is not None:
        return session_result
    
    # 2. Если сессий нет или они не отвечают, используем веб-проверку
    result = check_telegram_fast(username)
    if result is True:
        try:
            r = requests.get(f"https://fragment.com/username/{username}", timeout=2, allow_redirects=True)
            if "query=" in r.url:
                return True
            if "auction" in r.text.lower() or "for sale" in r.text.lower():
                return False
        except:
            pass
        return True
    return False

def generate_from_pattern(pattern):
    return ''.join(random.choice(consonants) if ch == 'C' else random.choice(vowels) for ch in pattern)

def generate_smart_nick(length=5):
    patterns = patterns_5 if length == 5 else patterns_6
    pattern = random.choice(patterns)
    nick = generate_from_pattern(pattern)
    for _ in range(5):
        if 'yy' in nick or 'aa' in nick or 'ii' in nick or 'uu' in nick:
            nick = generate_from_pattern(pattern)
        else: break
    return nick

def error_handler(func):
    def wrapper(message):
        try: return func(message)
        except Exception as e: logger.error(f"Ошибка: {e}")
    return wrapper

def check_subscription(user_id):
    try:
        status = bot.get_chat_member(REQUIRED_CHANNEL, user_id).status
        return status in ['member', 'administrator', 'creator']
    except: return True

def subscription_required(func):
    def wrapper(message):
        if check_subscription(message.from_user.id): return func(message)
        else:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("<tg-emoji emoji-id='4911656069207426158'>📢</tg-emoji> Подписаться", url=CHANNEL_LINK))
            bot.send_message(message.from_user.id, f"<tg-emoji emoji-id='4916105371858240403'>🔒</tg-emoji> <b>Подпишись на канал</b>\n\n{CHANNEL_LINK}", parse_mode='HTML', reply_markup=markup)
    return wrapper

def has_premium(user_id):
    user = get_user(user_id)
    if not user or not user['subscription_end']: return False
    try: return datetime.datetime.now() < datetime.datetime.strptime(user['subscription_end'], '%Y-%m-%d %H:%M:%S')
    except: return False

def get_available_searches(user_id):
    user = get_user(user_id)
    if not user: return BASE_SEARCHES
    if has_premium(user_id): return 999
    packages = user.get('search_packages', 0)
    if packages > 0: return packages
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    if user['last_search_date'] != today:
        update_user(user_id, searches_today=0, last_search_date=today)
        return BASE_SEARCHES
    return max(BASE_SEARCHES - (user['searches_today'] or 0), 0)

def use_search(user_id):
    user = get_user(user_id)
    if user:
        packages = user.get('search_packages', 0)
        if packages > 0:
            update_user(user_id, search_packages=packages - 1, total_searches=(user['total_searches'] or 0) + 1)
        else:
            update_user(user_id, searches_today=(user['searches_today'] or 0) + 1, total_searches=(user['total_searches'] or 0) + 1)

def add_found(user_id):
    user = get_user(user_id)
    if user: update_user(user_id, found_count=(user['found_count'] or 0) + 1)

def add_premium(user_id, days, from_ref=False):
    user = get_user(user_id)
    if not user: return
    now = datetime.datetime.now()
    new_end = now + datetime.timedelta(days=days)
    if user['subscription_end']:
        try:
            old = datetime.datetime.strptime(user['subscription_end'], '%Y-%m-%d %H:%M:%S')
            if old > now: new_end = old + datetime.timedelta(days=days)
        except: pass
    update_user(user_id, subscription_end=new_end.strftime('%Y-%m-%d %H:%M:%S'))
    try:
        text = f"<tg-emoji emoji-id='4918203446202467778'>💎</tg-emoji> <b>ПРЕМИУМ АКТИВИРОВАН</b>\n\n📅 До: {new_end.strftime('%d.%m.%Y')}"
        if from_ref: text = f"<tg-emoji emoji-id='4916105371858240403'>🔥</tg-emoji> <b>НАГРАДА ЗА РЕФЕРАЛОВ</b>\n\n{text}"
        bot.send_message(user_id, text, parse_mode='HTML')
    except: pass

def get_main_keyboard(user_id=None):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton("Поиск"),
        types.KeyboardButton("Статистика (бота)"),
        types.KeyboardButton("Профиль"),
        types.KeyboardButton("Премиум")
    ]
    if user_id == ADMIN_ID:
        buttons.append(types.KeyboardButton(f"{EMOJI['admin']} АДМИН"))
    markup.add(*buttons)
    return markup

def admin_inline_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        types.InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
        types.InlineKeyboardButton("💎 Выдать Premium", callback_data="admin_give_premium"),
        types.InlineKeyboardButton("📦 Выдать поиски", callback_data="admin_give_searches"),
        types.InlineKeyboardButton("🎁 Подарить Premium", callback_data="admin_gift"),
        types.InlineKeyboardButton("🚫 Бан", callback_data="admin_ban"),
        types.InlineKeyboardButton("✅ Разбан", callback_data="admin_unban"),
        types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("🗑️ Снять рефералов", callback_data="admin_removerefs"),
        types.InlineKeyboardButton("🔄 Сессии", callback_data="admin_sessions_menu")
    )
    return markup

def sessions_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Добавить сессию", callback_data="session_add"),
        types.InlineKeyboardButton("📋 Список сессий", callback_data="session_list"),
        types.InlineKeyboardButton("🔍 Проверить все сессии", callback_data="session_check_all"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
    )
    return markup

# ========== /start ==========
@bot.message_handler(commands=['start'])
@error_handler
def start(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        bot.send_message(user_id, "<tg-emoji emoji-id='5121063440311386962'>🚫</tg-emoji> <b>Вы заблокированы.</b>", parse_mode='HTML')
        return
    allowed, error_msg = check_rate_limit(user_id, 'start')
    if not allowed: bot.send_message(user_id, error_msg, parse_mode='HTML'); return
    username = message.from_user.username
    referrer_id = None
    if len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
            if referrer_id == user_id: referrer_id = None
        except: pass
    user, is_new = create_user(user_id, username, referrer_id)
    if is_new:
        bot.send_message(user_id, "<tg-emoji emoji-id='6082635604896520956'>🚀</tg-emoji> Проходим проверку...", parse_mode='HTML')
        time.sleep(1)
    if check_subscription(user_id):
        activate_referral(user_id)
        welcome = (f"<tg-emoji emoji-id='4918354603281482671'>⭐</tg-emoji> ДОБРО ПОЖАЛОВАТЬ!\n\n"
                  f"<tg-emoji emoji-id='4906943755644306322'>⭐</tg-emoji> У нас можно:\n"
                  f"<tg-emoji emoji-id='4902524693858222969'>⭐</tg-emoji> Поиск 5-6 букв\n"
                  f"<tg-emoji emoji-id='4902524693858222969'>⭐</tg-emoji> Поиск по слову\n"
                  f"<tg-emoji emoji-id='4902524693858222969'>⭐</tg-emoji> Поиск по фильтру\n\n"
                  f"<tg-emoji emoji-id='4918203446202467778'>💎</tg-emoji> <b>Premium от 49⭐</b> — безлимит + всё!\n"
                  f"<tg-emoji emoji-id='4916105371858240403'>⭐</tg-emoji> Бот иногда может выдавать юзернеймы которые заблокированы в ТГ или стоят на продаже")
        bot.send_photo(user_id, photo="https://i.postimg.cc/nhbMgpRy/1775474714965.png", caption=welcome, parse_mode='HTML', reply_markup=get_main_keyboard(user_id))
    else:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Подписаться на канал", url=CHANNEL_LINK))
        bot.send_message(user_id, "Сначала подпишись на наш канал", parse_mode='HTML', reply_markup=markup)

# ========== ПОИСК ==========
@bot.message_handler(func=lambda m: m.text == "Поиск")
@subscription_required
@error_handler
def search_menu_handler(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        bot.send_message(user_id, "<tg-emoji emoji-id='5121063440311386962'>🚫</tg-emoji> <b>Вы заблокированы.</b>", parse_mode='HTML')
        return
    sessions_count = len(available_clients)
    text = (f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> <b>Режим Буквы</b> — поиск свободных юзернеймов по количеству букв.\n\n"
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> <b>Слово</b> — Вводите основу, и бот найдет свободные ники.\n\n"
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> <b>Фильтр</b> — поиск по маске от 5 до 15 символов.\n\n"
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> <b>Ловушка</b> — уведомит, когда ник освободится.\n\n")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("5 букв", callback_data="search_mode_5"),
        types.InlineKeyboardButton("6 букв", callback_data="search_mode_6"),
        types.InlineKeyboardButton("Фильтр", callback_data="search_mode_filter"),
        types.InlineKeyboardButton("Ловушка", callback_data="search_mode_trap"),
        types.InlineKeyboardButton("Слово", callback_data="search_mode_word"),
        types.InlineKeyboardButton("Закрыть", callback_data="search_close")
    )
    bot.send_message(user_id, text, parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "search_close")
def search_close_handler(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)

def perform_search(user_id, length, msg=None):
    if get_available_searches(user_id) <= 0:
        bot.send_message(user_id, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Лимит исчерпан!</b>\n\n<tg-emoji emoji-id='4918203446202467778'>💎</tg-emoji> Купите премиум", parse_mode='HTML')
        return
    if not msg:
        msg = bot.send_message(user_id, f"<tg-emoji emoji-id='5134122666331996794'>🔍</tg-emoji> <b>Ищу {length}-буквенный ник...</b>", parse_mode='HTML')
    found_usernames = set()
    for i in range(SEARCH_ATTEMPTS):
        batch = [generate_smart_nick(length) for _ in range(5)]
        for username in batch:
            if username in found_usernames: continue
            found_usernames.add(username)
            if check_username_full(username):
                use_search(user_id)
                add_found(user_id)
                price_range = estimate_price(username)
                try:
                    with db_lock:
                        cursor.execute("INSERT INTO found (username, length, price, found_date, finder_id) VALUES (?, ?, ?, datetime('now'), ?)", 
                                     (username, length, price_range, user_id))
                        conn.commit()
                except: pass
                try: bot.delete_message(user_id, msg.message_id)
                except: pass
                searches_left = get_available_searches(user_id)
                prem_text = "Безлимит (Премиум)" if has_premium(user_id) else str(searches_left)
                win_text = (f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> <b>НИК НАЙДЕН!</b>\n\n"
                           f"<tg-emoji emoji-id='5084979757905347540'>📛</tg-emoji> Ник: @{username}\n"
                           f"<tg-emoji emoji-id='5084923566848213749'>🔤</tg-emoji> Букв: {length} букв\n\n"
                           f"Осталось поисков: {prem_text}\n"
                           f"<tg-emoji emoji-id='4911656069207426158'>📢</tg-emoji> Наш канал: {REQUIRED_CHANNEL}")
                search_markup = types.InlineKeyboardMarkup()
                search_markup.add(types.InlineKeyboardButton("Найти другой", callback_data=f"search_mode_{length}"))
                bot.send_message(user_id, win_text, parse_mode='HTML', reply_markup=search_markup)
                return
        if i % 5 == 0 and msg:
            try: bot.edit_message_text(f"<tg-emoji emoji-id='5134122666331996794'>🔍</tg-emoji> <b>Поиск...</b> {i+1}/{SEARCH_ATTEMPTS}", user_id, msg.message_id, parse_mode='HTML')
            except: pass
        time.sleep(0.05)
    if msg:
        bot.edit_message_text(f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Не удалось найти свободный ник. Попробуйте еще раз!</b>", user_id, msg.message_id, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == "search_mode_5")
@subscription_required
@error_handler
def search_5_handler(call):
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)
    allowed, error_msg = check_rate_limit(user_id)
    if not allowed: bot.send_message(user_id, error_msg, parse_mode='HTML'); return
    perform_search(user_id, 5, None)

@bot.callback_query_handler(func=lambda call: call.data == "search_mode_6")
@subscription_required
@error_handler
def search_6_handler(call):
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)
    allowed, error_msg = check_rate_limit(user_id)
    if not allowed: bot.send_message(user_id, error_msg, parse_mode='HTML'); return
    perform_search(user_id, 6, None)

@bot.callback_query_handler(func=lambda call: call.data == "search_mode_filter")
@subscription_required
def filter_menu_handler(call):
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)
    if not has_premium(user_id):
        bot.send_message(user_id, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Фильтр только для Premium!</b>\n\n<tg-emoji emoji-id='4918203446202467778'>💎</tg-emoji> Купить премиум", parse_mode='HTML')
        return
    filter_text = (f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> <b>ФИЛЬТР</b>\n\nВведите маску (5-15 символов)\nЗнак <code>?</code> — любая случайная буква.\n\nПример: <code>a?s?a?a</code>")
    msg = bot.send_photo(user_id, photo="https://i.postimg.cc/nhbMgpRy/1775474714965.png", caption=filter_text, parse_mode='HTML')
    bot.register_next_step_handler(msg, process_filter_new)

def process_filter_new(message):
    user_id = message.from_user.id
    allowed, error_msg = check_rate_limit(user_id)
    if not allowed: bot.send_message(user_id, error_msg, parse_mode='HTML'); return
    mask_input = message.text.strip().lower()
    if not mask_input or len(mask_input) < 5 or len(mask_input) > 15:
        bot.send_message(user_id, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Маска должна быть от 5 до 15 символов!</b>", parse_mode='HTML'); return
    msg = bot.send_message(user_id, f"<tg-emoji emoji-id='5134122666331996794'>🔍</tg-emoji> <b>Ищу по маске '{mask_input}'...</b>", parse_mode='HTML')
    checked = 0
    found_set = set()
    for i in range(FILTER_ATTEMPTS):
        username = ""
        for ch in mask_input:
            if ch == '?': username += random.choice(all_letters)
            elif ch.isalpha(): username += ch
            else:
                bot.edit_message_text(f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Разрешены только буквы и знак ?</b>", user_id, msg.message_id, parse_mode='HTML'); return
        if len(username) < 5 or len(username) > 32 or username in found_set: continue
        found_set.add(username)
        checked += 1
        if check_username_full(username):
            use_search(user_id)
            add_found(user_id)
            price_range = estimate_price(username)
            try: bot.delete_message(user_id, msg.message_id)
            except: pass
            prem_text = "Безлимит (Премиум)" if has_premium(user_id) else str(get_available_searches(user_id))
            win_text = (f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> <b>НИК НАЙДЕН!</b>\n\n"
                       f"<tg-emoji emoji-id='5084979757905347540'>📛</tg-emoji> Ник: @{username}\n"
                       f"<tg-emoji emoji-id='5084923566848213749'>🔤</tg-emoji> Символов: {len(username)}\n\n"
                       f"Осталось поисков: {prem_text}\n"
                       f"<tg-emoji emoji-id='4911656069207426158'>📢</tg-emoji> Наш канал: {REQUIRED_CHANNEL}")
            bot.send_message(user_id, win_text, parse_mode='HTML')
            return
        if i % 5 == 0:
            try: bot.edit_message_text(f"<tg-emoji emoji-id='5134122666331996794'>🔍</tg-emoji> <b>Поиск...</b> {checked}/{FILTER_ATTEMPTS}", user_id, msg.message_id, parse_mode='HTML')
            except: pass
        time.sleep(0.05)
    bot.edit_message_text(f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Ничего не найдено</b>\nПопробуй другую маску!", user_id, msg.message_id, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == "search_mode_trap")
@subscription_required
def trap_menu_handler(call):
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)
    if not has_premium(user_id):
        bot.send_message(user_id, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Ловушка только для Premium!</b>\n\n<tg-emoji emoji-id='4918203446202467778'>💎</tg-emoji> Купить премиум", parse_mode='HTML')
        return
    msg = bot.send_photo(user_id, photo="https://i.postimg.cc/nhbMgpRy/1775474714965.png", caption=f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> <b>ЛОВУШКА</b>\n\nВведи ник без @, например <code>tergut</code>", parse_mode='HTML')
    bot.register_next_step_handler(msg, process_trap)

def process_trap(message):
    user_id = message.from_user.id
    allowed, error_msg = check_rate_limit(user_id)
    if not allowed: bot.send_message(user_id, error_msg, parse_mode='HTML'); return
    is_valid, result = validate_username(message.text)
    if not is_valid: bot.send_message(user_id, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Ошибка:</b> {result}", parse_mode='HTML'); return
    target = result
    with db_lock:
        cursor.execute("SELECT COUNT(*) FROM traps WHERE user_id = ? AND status = 'active'", (user_id,))
        if cursor.fetchone()[0] >= 3:
            bot.send_message(user_id, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Максимум 3 ловушки!</b>", parse_mode='HTML'); return
    if check_username_full(target):
        bot.send_message(user_id, f"<tg-emoji emoji-id='5123163417326126159'>✅</tg-emoji> <b>НИК УЖЕ СВОБОДЕН</b>\n\n@{target}\n\n🔗 https://t.me/{target}", parse_mode='HTML')
        return
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with db_lock:
        cursor.execute("INSERT INTO traps (user_id, target_username, status, created_date) VALUES (?, ?, 'active', ?)", (user_id, target, now))
        conn.commit()
    bot.send_message(user_id, f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> <b>ЛОВУШКА УСТАНОВЛЕНА!</b>\n\n🎯 @{target}\n<tg-emoji emoji-id='5134438483867206614'>⏱️</tg-emoji> Сообщу, когда освободится", parse_mode='HTML')

def check_traps():
    while True:
        try:
            time.sleep(30)
            with db_lock:
                cursor.execute("SELECT id, user_id, target_username FROM traps WHERE status = 'active'")
                traps = cursor.fetchall()
            for trap_id, user_id, target in traps:
                if check_username_full(target):
                    with db_lock:
                        cursor.execute("UPDATE traps SET status = 'completed' WHERE id = ?", (trap_id,))
                        conn.commit()
                    try:
                        bot.send_message(user_id, f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> <b>ЛОВУШКА СРАБОТАЛА!</b>\n\n✅ @{target} теперь свободен!\n\n🔗 https://t.me/{target}", parse_mode='HTML')
                    except: pass
        except: pass

threading.Thread(target=check_traps, daemon=True).start()

@bot.callback_query_handler(func=lambda call: call.data == "search_mode_word")
@subscription_required
def word_search_menu_handler(call):
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)
    if not has_premium(user_id):
        bot.send_message(user_id, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>СЛОВО только для Premium!</b>\n\n<tg-emoji emoji-id='4918203446202467778'>💎</tg-emoji> Купить премиум", parse_mode='HTML')
        return
    bot.send_photo(user_id, photo="https://i.postimg.cc/nhbMgpRy/1775474714965.png", caption=f"🔤 <b>СЛОВО</b>\n\nВведите основу (например: <code>style</code>)\nБот найдет свободные ники с этим корнем\nМинимум 3 буквы, максимум 10 букв", parse_mode='HTML')
    bot.register_next_step_handler(call.message, process_word_search_new)

def process_word_search_new(message):
    user_id = message.from_user.id
    allowed, error_msg = check_rate_limit(user_id)
    if not allowed: bot.send_message(user_id, error_msg, parse_mode='HTML'); return
    word = message.text.strip().lower()
    if len(word) < 3 or len(word) > 10 or not word.isalpha():
        bot.send_message(user_id, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Слово должно быть 3-10 букв!</b>", parse_mode='HTML'); return
    use_search(user_id)
    msg = bot.send_message(user_id, f"🔤 <b>Поиск ников со словом '{word}'...</b>", parse_mode='HTML')
    
    suffixes = [
        'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
        'aa', 'ab', 'ac', 'ad', 'ae', 'af', 'ag', 'ah', 'ai', 'aj', 'ak', 'al', 'am', 'an', 'ao', 'ap', 'aq', 'ar', 'as', 'at', 'au', 'av', 'aw', 'ax', 'ay', 'az',
        'tv', 'cc', 'gg', 'ss', 'zz', 'xx', 'yy', 'tt', 'pp', 'dd', 'ff', 'll', 'mm', 'nn', 'rr', 'vv', 'ww',
        'ok', 'up', 'on', 'in', 'it', 'is', 'us', 'uk', 'io', 'ai', 'eu', 'ru', 'de', 'fr', 'es', 'pl', 'se'
    ]
    
    prefixes = [
        'i', 'a', 'e', 'o', 'u', 'x', 'z', 'v', 'k', 'j', 'd', 'r', 'f', 'g', 't', 'm', 'l', 's', 'p', 'q', 'y', 'h', 'b', 'c', 'n', 'w',
        'my', 'mr', 'ms', 'dr', 'dj', 'mc', 'la', 'le', 'da', 'de', 'do', 'el', 'ka', 'ki', 'ko', 'ma', 'mi', 'mo',
        'the', 'real', 'just', 'best', 'super', 'pro', 'top', 'ultra', 'mega', 'hyper', 'cyber', 'tech', 'nexus',
        'alpha', 'beta', 'gamma', 'delta', 'omega', 'sigma', 'prime', 'elite', 'crypto', 'neo', 'pixel', 'byte',
        'dark', 'light', 'fire', 'ice', 'wind', 'earth', 'water', 'sky', 'star', 'moon', 'sun', 'void', 'zero'
    ]
    
    for i in range(SEARCH_ATTEMPTS):
        username = word + random.choice(suffixes) if i % 2 == 0 else random.choice(prefixes) + word
        if len(username) < 5 or len(username) > 32: continue
        if check_username_full(username):
            add_found(user_id)
            price_range = estimate_price(username)
            try: bot.delete_message(user_id, msg.message_id)
            except: pass
            win_text = (f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> <b>НИК НАЙДЕН!</b>\n\n"
                       f"<tg-emoji emoji-id='5084979757905347540'>📛</tg-emoji> Ник: @{username}\n"
                       f"<tg-emoji emoji-id='5084923566848213749'>🔤</tg-emoji> Букв: {len(username)}\n\n"
                       f"<tg-emoji emoji-id='4911656069207426158'>📢</tg-emoji> Наш канал: {REQUIRED_CHANNEL}")
            bot.send_message(user_id, win_text, parse_mode='HTML')
            return
        time.sleep(0.05)
    bot.edit_message_text(f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Ничего не найдено</b>\n\nПопробуй другое слово!", user_id, msg.message_id, parse_mode='HTML')

# ========== ПРОФИЛЬ ==========
@bot.message_handler(func=lambda m: m.text == "Профиль")
def profile(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user: user, _ = create_user(user_id, message.from_user.username); user = get_user(user_id)
    prem_status = "<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> Нет"
    if user['subscription_end']:
        try:
            end = datetime.datetime.strptime(user['subscription_end'], '%Y-%m-%d %H:%M:%S')
            if datetime.datetime.now() < end: prem_status = f"<tg-emoji emoji-id='5123163417326126159'>✅</tg-emoji> есть до {end.strftime('%d.%m.%Y')}"
        except: pass
    with db_lock:
        cursor.execute("SELECT COUNT(*) FROM traps WHERE user_id = ? AND status = 'active'", (user_id,))
        traps_active = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM traps WHERE user_id = ? AND status = 'completed'", (user_id,))
        traps_completed = cursor.fetchone()[0]
    registration_date = user.get('created_date', 'Неизвестно')
    if registration_date and registration_date != 'Неизвестно':
        try:
            date_obj = datetime.datetime.strptime(registration_date, '%Y-%m-%d %H:%M:%S')
            registration_date = date_obj.strftime('%d.%m.%Y %H:%M')
        except: pass
    username_text = f"@{user['username']}" if user['username'] else "Нет"
    text = (f"<tg-emoji emoji-id='4904848288345228262'>⭐</tg-emoji> ПРОФИЛЬ\n\n"
            f"<tg-emoji emoji-id='5116512467194741904'>⭐</tg-emoji> ID: <code>{user_id}</code>\n"
            f"<tg-emoji emoji-id='5116512467194741904'>⭐</tg-emoji> Юзернейм: {username_text}\n\n"
            f"<tg-emoji emoji-id='5116175844837950263'>⭐</tg-emoji> Премиум: {prem_status}\n"
            f"<tg-emoji emoji-id='5104960787579929462'>⭐</tg-emoji> Сегодня: {user.get('searches_today', 0)}/3\n"
            f"<tg-emoji emoji-id='5122933683820430249'>⭐</tg-emoji> Всего поисков: {user.get('total_searches', 0)}\n"
            f"<tg-emoji emoji-id='5116298753917060171'>⭐</tg-emoji> Найдено ников: {user.get('found_count', 0)}\n"
            f"<tg-emoji emoji-id='4916086774649848789'>⭐</tg-emoji> Ловушек: {traps_active} активных / {traps_completed} сработало\n"
            f"<tg-emoji emoji-id='4916086774649848789'>⭐</tg-emoji> Рефералов: {user.get('referrals_count', 0)} чел.\n\n"
            f"<tg-emoji emoji-id='5118357331742032622'>⭐</tg-emoji> Регистрация: {registration_date}")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("Рефералка", callback_data="profile_referral"), types.InlineKeyboardButton("🏆 Топ", callback_data="profile_top"))
    bot.send_photo(user_id, photo="https://i.postimg.cc/nhbMgpRy/1775474714965.png", caption=text, parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "profile_referral")
def referral_callback(call):
    user_id = call.from_user.id
    user = get_user(user_id)
    if not user: user, _ = create_user(user_id, call.from_user.username); user = get_user(user_id)
    link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    total_refs = user['referrals_count'] if user else 0
    next_reward_text = "5 реф - 1 дн Premium"
    if total_refs >= 20: next_reward_text = "Макс. награда достигнута"
    elif total_refs >= 12: next_reward_text = "20 реф - 4 дн Premium"
    elif total_refs >= 8: next_reward_text = "15 реф - 3 дн Premium"
    elif total_refs >= 5: next_reward_text = "10 реф - 2 дн Premium"
    text = (f"<tg-emoji emoji-id='5123237479742178762'>⭐</tg-emoji> РЕФЕРАЛЬНАЯ СИСТЕМА\n\n"
            f"<tg-emoji emoji-id='4916086774649848789'>⭐</tg-emoji> Твоя ссылка: <code>{link}</code>\n\n"
            f"<tg-emoji emoji-id='4906943755644306322'>⭐</tg-emoji> Статистика:\n"
            f"<tg-emoji emoji-id='4918087434840834979'>⭐</tg-emoji> Приглашено: {total_refs}\n\n"
            f"<tg-emoji emoji-id='4916105371858240403'>⭐</tg-emoji> НАГРАДЫ:\n"
            f"5 рефералов - 1 дн Premium\n10 рефералов - 2 дн Premium\n15 рефералов - 3 дн Premium\n20 рефералов - 4 дн Premium\n"
            f"<tg-emoji emoji-id='5134202243486057363'>⭐</tg-emoji> Следующая награда: {next_reward_text}\n\n"
            f"<tg-emoji emoji-id='5116275208906343429'>⭐</tg-emoji> Реферал засчитывается после подписки на группу!")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="profile_back"))
    bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "profile_top")
def top_callback(call):
    with db_lock:
        cursor.execute("SELECT username, user_id, referrals_count FROM users WHERE referrals_count > 0 ORDER BY referrals_count DESC LIMIT 10")
        top_users = cursor.fetchall()
    text = f"<tg-emoji emoji-id='4904973211763999824'>⭐</tg-emoji> ТОП РЕФЕРАЛОВ <tg-emoji emoji-id='4904832912362309275'>🏆</tg-emoji>\n\n"
    if not top_users: text += "Пока нет участников"
    else:
        for i, (username, uid, refs) in enumerate(top_users, 1):
            name = f"@{username}" if username else f"ID {uid}"
            text += f"<tg-emoji emoji-id='4904848288345228262'>⭐</tg-emoji> {i}. {name} — {refs} реф.\n"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="profile_back"))
    bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "profile_back")
def profile_back_callback(call): profile(call)

# ========== СТАТИСТИКА ==========
@bot.message_handler(func=lambda m: m.text == "Статистика (бота)")
def stats(message):
    with db_lock:
        cursor.execute("SELECT COUNT(*) FROM users"); total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_end > datetime('now')"); premium_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM found"); found_nicks = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM traps WHERE status = 'active'"); active_traps = cursor.fetchone()[0]
        try: cursor.execute("SELECT SUM(total_searches) FROM users"); total_searches = cursor.fetchone()[0] or 0
        except: total_searches = 0
    text = (f"<tg-emoji emoji-id='4906943755644306322'>⭐</tg-emoji> СТАТИСТИКА БОТА\n\n"
            f"<tg-emoji emoji-id='4904848288345228262'>⭐</tg-emoji> Пользователей: {total_users}\n"
            f"<tg-emoji emoji-id='4913497231492908158'>⭐</tg-emoji> Премиум: {premium_users}\n"
            f"<tg-emoji emoji-id='5084923566848213749'>⭐</tg-emoji> Найдено ников: {found_nicks}\n"
            f"<tg-emoji emoji-id='5098094273039959279'>⭐</tg-emoji> Активных ловушек: {active_traps}\n"
            f"<tg-emoji emoji-id='5116414868357907335'>⭐</tg-emoji> Всего поисков: {total_searches}")
    bot.send_message(message.chat.id, text, parse_mode='HTML')

# ========== ПРЕМИУМ ==========
@bot.message_handler(func=lambda m: m.text == "Премиум")
def premium(message):
    user_id = message.from_user.id if hasattr(message, 'from_user') else message.chat.id
    text = (f"<tg-emoji emoji-id='4918203446202467778'>💎</tg-emoji> ПРЕМИУМ ПОДПИСКА\n\n"
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> ФУНКЦИИ:\n"
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> Фильтр по маске\n"
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> Ловушка на ник\n"
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> Слово\n"
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> Безлимитный поиск")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("1 день", callback_data="premium_sel_1"),
        types.InlineKeyboardButton("3 дня", callback_data="premium_sel_3"),
        types.InlineKeyboardButton("7 дней", callback_data="premium_sel_7"),
        types.InlineKeyboardButton("30 дней", callback_data="premium_sel_30")
    )
    bot.send_photo(user_id, photo="https://i.postimg.cc/nhbMgpRy/1775474714965.png", caption=text, parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('premium_sel_'))
def premium_selection_callback(call):
    days = int(call.data.split('_')[-1])
    price_stars = PREMIUM_PRICES[days]
    prices_crypto = {1: 0.74, 3: 1.80, 7: 3.15, 30: 6.75}
    price_usd = prices_crypto[days]
    text = (f"<tg-emoji emoji-id='5116093437300442328'>💳</tg-emoji> Способ оплаты\n\n"
            f"Вы выбрали:\nТариф: {days} дн.\nЦена: {price_stars} ⭐ / ${price_usd}")
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("Stars", callback_data=f"premium_stars_{days}"),
        types.InlineKeyboardButton("Ton", callback_data=f"premium_crypto_ton_{days}"),
        types.InlineKeyboardButton("Usdt", callback_data=f"premium_crypto_usdt_{days}")
    )
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="premium_back"))
    bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "premium_back")
def premium_back_callback(call):
    premium(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith('premium_stars_'))
def premium_stars_callback(call):
    user_id = call.from_user.id
    try:
        days = int(call.data.split('_')[-1])
        price = PREMIUM_PRICES[days]
        bot.answer_callback_query(call.id)
        bot.send_invoice(chat_id=user_id, title=f"Premium на {days} дней", description=f"Оплата премиум-подписки на {days} дней",
                        invoice_payload=f"premium_stars_{user_id}_{days}", provider_token="", currency="XTR",
                        prices=[types.LabeledPrice(label=f"Premium {days} дн", amount=price)])
    except Exception as e: logger.error(f"Error: {e}")

@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout_query(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def process_successful_payment(message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("premium_stars_"):
        parts = payload.split('_')
        user_id = int(parts[2]); days = int(parts[3])
        add_premium(user_id, days)
        bot.send_message(user_id, f"🎉 <b>Оплата прошла успешно!</b>\n\nВы получили Premium на {days} дней.\nСпасибо за поддержку!", parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('premium_crypto_'))
def premium_crypto_callback(call):
    user_id = call.from_user.id
    parts = call.data.split('_')
    days_str = parts[-1]; asset_pref = parts[-2]
    if not days_str.isdigit(): bot.answer_callback_query(call.id, "Ошибка!", show_alert=True); return
    days = int(days_str)
    prices = {1: 0.74, 3: 1.80, 7: 3.15, 30: 6.75}
    price = prices[days]
    bot.answer_callback_query(call.id)
    try:
        req_json = {"amount": price, "currency_type": "fiat", "fiat": "USD", "description": f"Premium {days} days", "payload": f"premium_{user_id}_{days}"}
        if asset_pref.lower() == "ton": req_json["accepted_assets"] = "TON"
        elif asset_pref.lower() == "usdt": req_json["accepted_assets"] = "USDT"
        response = requests.post("https://pay.crypt.bot/api/createInvoice", headers={"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}, json=req_json, timeout=10)
        data = response.json()
        if data.get('ok'):
            invoice_url = data['result']['bot_invoice_url']; invoice_id = data['result']['invoice_id']
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(f"💳 Оплатить ${price}", url=invoice_url), types.InlineKeyboardButton("✅ Проверить", callback_data=f"check_premium_crypto_{invoice_id}_{days}"))
            bot.send_message(user_id, f"💳 <b>ОПЛАТА КРИПТОЙ</b>\n\n💰 Сумма: ${price}\n📦 Пакет: {days} дней\n\nНажмите кнопку ниже:", parse_mode='HTML', reply_markup=markup)
        else: bot.send_message(user_id, "❌ Ошибка создания платежа.", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        bot.send_message(user_id, "❌ Ошибка.", parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('check_premium_crypto_'))
def check_premium_crypto_callback(call):
    user_id = call.from_user.id
    parts = call.data.split('_')
    invoice_id = parts[3]; days = int(parts[4])
    if check_crypto_payment(invoice_id):
        add_premium(user_id, days)
        bot.answer_callback_query(call.id, f"✅ Premium на {days} дн!", show_alert=True)
        bot.edit_message_text(f"✅ <b>ПРЕМИУМ АКТИВИРОВАН</b>\n\n📅 На {days} дней", user_id, call.message.message_id, parse_mode='HTML')
    else: bot.answer_callback_query(call.id, "⏳ Оплата не найдена", show_alert=True)

# ==================== АДМИН ПАНЕЛЬ ====================

@bot.message_handler(commands=['admin'])
def admin_panel_cmd(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Нет доступа")
        return
    show_admin_panel(message.chat.id)

def show_admin_panel(chat_id):
    text = f"{EMOJI['admin']} <b>АДМИН ПАНЕЛЬ</b>\n\nВыберите действие:"
    bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def admin_stats_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    with db_lock:
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_end > datetime('now')")
        premium_users = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(total_searches) FROM users")
        total_searches = cursor.fetchone()[0] or 0
        cursor.execute("SELECT SUM(found_count) FROM users")
        total_found = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM users WHERE banned = 1")
        banned = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM sessions")
        total_sessions = cursor.fetchone()[0]
    text = (f"📊 <b>СТАТИСТИКА</b>\n\n"
            f"👥 Всего: {total_users}\n"
            f"💎 Premium: {premium_users}\n"
            f"🚫 Забанено: {banned}\n"
            f"🔍 Поисков: {total_searches}\n"
            f"✅ Найдено: {total_found}\n"
            f"🔄 Сессий: {total_sessions}")
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=admin_inline_menu())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_users")
def admin_users_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    with db_lock:
        cursor.execute("SELECT user_id, username, referrals_count, banned FROM users ORDER BY created_date DESC LIMIT 50")
        users = cursor.fetchall()
    if not users:
        text = "👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n\nНет пользователей"
    else:
        text = "👥 <b>ПОСЛЕДНИЕ 50 ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
        for uid, username, refs, banned in users:
            name = f"@{username}" if username else f"ID {uid}"
            ban = "🚫" if banned else ""
            text += f"{name} — {refs} реф {ban}\n"
    if len(text) > 4000:
        text = text[:4000] + "\n\n... и ещё"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=admin_inline_menu())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_give_premium")
def admin_give_premium_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("💎 Введите ID пользователя и количество дней через пробел:\nПример: `123456789 7`", 
                          call.message.chat.id, call.message.message_id, parse_mode='HTML')
    bot.register_next_step_handler(call.message, admin_give_premium_step)

def admin_give_premium_step(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split()
        user_id = int(parts[0])
        days = int(parts[1])
        add_premium(user_id, days)
        bot.send_message(message.chat.id, f"✅ Premium {days}дн выдан пользователю {user_id}", reply_markup=admin_inline_menu())
    except:
        bot.send_message(message.chat.id, "❌ Ошибка. Используйте: ID ДНИ", reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_give_searches")
def admin_give_searches_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("📦 Введите ID пользователя и количество поисков через пробел:\nПример: `123456789 10`", 
                          call.message.chat.id, call.message.message_id, parse_mode='HTML')
    bot.register_next_step_handler(call.message, admin_give_searches_step)

def admin_give_searches_step(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split()
        user_id = int(parts[0])
        amount = int(parts[1])
        add_search_packages(user_id, amount)
        bot.send_message(message.chat.id, f"✅ {amount} поисков выдано пользователю {user_id}", reply_markup=admin_inline_menu())
    except:
        bot.send_message(message.chat.id, "❌ Ошибка. Используйте: ID КОЛИЧЕСТВО", reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_gift")
def admin_gift_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("🎁 Введите ID пользователя и количество дней через пробел:\nПример: `123456789 7`", 
                          call.message.chat.id, call.message.message_id, parse_mode='HTML')
    bot.register_next_step_handler(call.message, admin_gift_step)

def admin_gift_step(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split()
        receiver_id = int(parts[0])
        days = int(parts[1])
        add_premium(receiver_id, days)
        create_gift(ADMIN_ID, receiver_id, days, "admin")
        bot.send_message(message.chat.id, f"✅ Подарен Premium {days}дн пользователю {receiver_id}", reply_markup=admin_inline_menu())
        try:
            bot.send_message(receiver_id, f"🎁 <b>ВАМ ПОДАРИЛИ ПРЕМИУМ!</b>\n\n⏱️ Срок: {days} дней\nОт: Администратор", parse_mode='HTML')
        except:
            pass
    except:
        bot.send_message(message.chat.id, "❌ Ошибка. Используйте: ID ДНИ", reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_ban")
def admin_ban_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("🚫 Введите ID пользователя для бана:", call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(call.message, admin_ban_step)

def admin_ban_step(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        user_id = int(message.text.strip())
        update_user(user_id, banned=1)
        bot.send_message(message.chat.id, f"🚫 Пользователь {user_id} забанен", reply_markup=admin_inline_menu())
        try:
            bot.send_message(user_id, "🚫 <b>Вы заблокированы в боте.</b>", parse_mode='HTML')
        except:
            pass
    except:
        bot.send_message(message.chat.id, "❌ Ошибка. Введите ID", reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_unban")
def admin_unban_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("✅ Введите ID пользователя для разбана:", call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(call.message, admin_unban_step)

def admin_unban_step(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        user_id = int(message.text.strip())
        update_user(user_id, banned=0)
        bot.send_message(message.chat.id, f"✅ Пользователь {user_id} разбанен", reply_markup=admin_inline_menu())
        try:
            bot.send_message(user_id, "✅ <b>Вы разблокированы в боте.</b>", parse_mode='HTML')
        except:
            pass
    except:
        bot.send_message(message.chat.id, "❌ Ошибка. Введите ID", reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def admin_broadcast_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("📢 Введите текст для рассылки:", call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(call.message, admin_broadcast_step)

def admin_broadcast_step(message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text
    if not text:
        bot.send_message(message.chat.id, "❌ Текст не может быть пустым", reply_markup=admin_inline_menu())
        return
    with db_lock:
        cursor.execute("SELECT user_id FROM users WHERE banned = 0")
        users = cursor.fetchall()
    success = 0
    failed = 0
    status_msg = bot.send_message(message.chat.id, f"📢 Рассылка... 0/{len(users)}")
    for user_id, in users:
        try:
            bot.send_message(user_id, text, parse_mode='HTML')
            success += 1
            time.sleep(0.05)
        except:
            failed += 1
        if success % 10 == 0:
            try:
                bot.edit_message_text(f"📢 Рассылка... {success}/{len(users)}", message.chat.id, status_msg.message_id)
            except:
                pass
    bot.edit_message_text(f"✅ Готово! ✅{success} ❌{failed}", message.chat.id, status_msg.message_id, reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_removerefs")
def admin_removerefs_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("🗑️ Введите ID пользователя и количество рефералов для снятия через пробел:\nПример: `123456789 5`", 
                          call.message.chat.id, call.message.message_id, parse_mode='HTML')
    bot.register_next_step_handler(call.message, admin_removerefs_step)

def admin_removerefs_step(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split()
        user_id = int(parts[0])
        amount = int(parts[1])
        user = get_user(user_id)
        if not user:
            bot.send_message(message.chat.id, "❌ Пользователь не найден", reply_markup=admin_inline_menu())
            return
        current = user.get('referrals_count', 0)
        new_count = max(0, current - amount)
        update_user(user_id, referrals_count=new_count)
        bot.send_message(message.chat.id, f"🗑️ Снято {amount} реф. у {user_id}\nБыло: {current} → Стало: {new_count}", reply_markup=admin_inline_menu())
    except:
        bot.send_message(message.chat.id, "❌ Ошибка. Используйте: ID КОЛИЧЕСТВО", reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_sessions_menu")
def admin_sessions_menu_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("🔄 <b>Управление сессиями</b>\n\nВыберите действие:", 
                          call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=sessions_menu())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_back")
def admin_back_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    show_admin_panel(call.message.chat.id)
    bot.answer_callback_query(call.id)

# ==================== УПРАВЛЕНИЕ СЕССИЯМИ ====================

temp_session_data = {}

def parse_proxy(proxy_str):
    if not proxy_str or proxy_str.lower() == 'нет':
        return None
    try:
        if '@' in proxy_str:
            auth, addr = proxy_str.split('@')
            user, pwd = auth.split(':')
            ip, port = addr.split(':')
            return {
                'proxy_type': 'socks5',
                'addr': ip,
                'port': int(port),
                'username': user,
                'password': pwd
            }
        else:
            ip, port = proxy_str.split(':')
            return {
                'proxy_type': 'socks5',
                'addr': ip,
                'port': int(port)
            }
    except:
        return None

@bot.callback_query_handler(func=lambda call: call.data == "session_add")
def session_add_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    temp_session_data[call.from_user.id] = {}
    bot.edit_message_text(
        "Введите номер телефона в формате +7XXXXXXXXXX:\n(или 'отмена')",
        call.message.chat.id, call.message.message_id
    )
    bot.register_next_step_handler(call.message, session_add_phone_step)
    bot.answer_callback_query(call.id)

def session_add_phone_step(message):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text.lower() == 'отмена':
        temp_session_data.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, "Отменено", reply_markup=admin_inline_menu())
        return
    phone = message.text.strip()
    if not phone.startswith('+'):
        phone = '+' + phone
    temp_session_data[message.from_user.id]['phone'] = phone
    bot.send_message(message.chat.id, "Введите прокси (user:pass@ip:port) или 'нет':")
    bot.register_next_step_handler(message, session_add_proxy_step)

def session_add_proxy_step(message):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text.lower() == 'отмена':
        temp_session_data.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, "Отменено", reply_markup=admin_inline_menu())
        return
    proxy_str = message.text.strip()
    proxy = parse_proxy(proxy_str) if proxy_str.lower() != 'нет' else None
    temp_session_data[message.from_user.id]['proxy'] = proxy
    bot.send_message(message.chat.id, "Отправляю запрос кода...")
    asyncio.run_coroutine_threadsafe(
        send_code_request(message.chat.id, message.from_user.id, 
                         temp_session_data[message.from_user.id]['phone'],
                         proxy),
        loop
    )

async def send_code_request(chat_id, user_id, phone, proxy):
    session_name = f"session_{int(time.time())}_{user_id}"
    client = TelegramClient(session_name, API_ID, API_HASH, proxy=proxy)
    try:
        await client.connect()
        await client.send_code_request(phone)
        bot.send_message(chat_id, f"Код отправлен на {phone}. Введите его:")
        temp_session_data[user_id]['client'] = client
        temp_session_data[user_id]['session_name'] = session_name
        temp_session_data[user_id]['phone'] = phone
        temp_session_data[user_id]['proxy'] = proxy
        bot.register_next_step_handler_by_chat_id(chat_id, session_enter_code_step, user_id)
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка: {str(e)[:100]}")
        temp_session_data.pop(user_id, None)
        await client.disconnect()

def session_enter_code_step(message, user_id):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text.lower() == 'отмена':
        temp_session_data.pop(user_id, None)
        bot.send_message(message.chat.id, "Отменено", reply_markup=admin_inline_menu())
        return
    code = message.text.strip()
    data = temp_session_data.get(user_id)
    if not data:
        bot.send_message(message.chat.id, "Сессия не найдена, начните заново")
        return
    bot.send_message(message.chat.id, "Проверяю код...")
    asyncio.run_coroutine_threadsafe(
        complete_session_add(message.chat.id, user_id, code),
        loop
    )

async def complete_session_add(chat_id, user_id, code):
    data = temp_session_data.get(user_id)
    if not data:
        bot.send_message(chat_id, "Данные сессии потеряны")
        return
    client = data['client']
    session_name = data['session_name']
    phone = data['phone']
    proxy = data['proxy']
    try:
        await client.sign_in(phone, code)
        me = await client.get_me()
        add_session_to_db(session_name, phone, str(proxy) if proxy else None)
        with sessions_lock:
            sessions_clients[session_name] = client
        update_session_status(session_name, 'active')
        bot.send_message(chat_id, f"Сессия добавлена!\n{me.first_name} (@{me.username})\n{phone}")
        show_admin_panel(chat_id)
    except SessionPasswordNeededError:
        bot.send_message(chat_id, "Введите пароль 2FA:")
        bot.register_next_step_handler_by_chat_id(chat_id, session_enter_password_step, user_id, session_name, phone, proxy)
        return
    except PhoneCodeInvalidError:
        bot.send_message(chat_id, "Неверный код. Попробуйте снова.")
        bot.register_next_step_handler_by_chat_id(chat_id, session_enter_code_step, user_id)
        return
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка: {str(e)[:100]}")
    finally:
        temp_session_data.pop(user_id, None)

def session_enter_password_step(message, user_id, session_name, phone, proxy):
    if message.from_user.id != ADMIN_ID:
        return
    password = message.text.strip()
    data = temp_session_data.get(user_id)
    if not data:
        bot.send_message(message.chat.id, "Данные сессии потеряны")
        return
    client = data['client']
    asyncio.run_coroutine_threadsafe(
        finalize_session_with_password(message.chat.id, user_id, client, session_name, phone, proxy, password),
        loop
    )

async def finalize_session_with_password(chat_id, user_id, client, session_name, phone, proxy, password):
    try:
        await client.sign_in(password=password)
        me = await client.get_me()
        add_session_to_db(session_name, phone, str(proxy) if proxy else None)
        with sessions_lock:
            sessions_clients[session_name] = client
        update_session_status(session_name, 'active')
        bot.send_message(chat_id, f"Сессия добавлена!\n{me.first_name} (@{me.username})\n{phone}")
        show_admin_panel(chat_id)
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка: {str(e)[:100]}")
    finally:
        temp_session_data.pop(user_id, None)

@bot.callback_query_handler(func=lambda call: call.data == "session_list")
def session_list_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    sessions = get_all_sessions()
    if not sessions:
        text = "Список сессий\n\nНет добавленных сессий"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=sessions_menu())
        bot.answer_callback_query(call.id)
        return
    text = "Список сессий\n\n"
    for sid, name, phone, proxy, is_active, status in sessions:
        status_emoji = "V" if status == 'active' else "X"
        proxy_show = "Proxy: +" if proxy else "Proxy: -"
        text += f"{status_emoji} {name}\n   {phone}\n   {proxy_show}\n   Status: {status}\n   ID: {sid}\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for sid, name, phone, proxy, is_active, status in sessions:
        markup.add(types.InlineKeyboardButton(f"Удалить {name}", callback_data=f"session_del_{sid}"))
    markup.add(types.InlineKeyboardButton("Назад", callback_data="admin_sessions_menu"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("session_del_"))
def session_del_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    sid = int(call.data.split('_')[2])
    with db_lock:
        cursor.execute("SELECT session_name FROM sessions WHERE id = ?", (sid,))
        row = cursor.fetchone()
        session_name = row[0] if row else None
    delete_session(sid)
    if session_name:
        with sessions_lock:
            if session_name in sessions_clients:
                try:
                    asyncio.run_coroutine_threadsafe(sessions_clients[session_name].disconnect(), loop)
                except:
                    pass
                del sessions_clients[session_name]
                refresh_available_clients()
        try:
            os.remove(f"{session_name}.session")
        except:
            pass
    bot.answer_callback_query(call.id, "Сессия удалена")
    session_list_callback(call)

@bot.callback_query_handler(func=lambda call: call.data == "session_check_all")
def session_check_all_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    bot.edit_message_text("Проверка всех сессий, пожалуйста, подождите...", 
                          call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "Начинаю проверку сессий...")
    asyncio.run_coroutine_threadsafe(check_all_sessions_async(call.message.chat.id), loop)
    bot.answer_callback_query(call.id)

async def check_all_sessions_async(chat_id):
    sessions = get_all_sessions()
    if not sessions:
        bot.send_message(chat_id, "Нет добавленных сессий")
        return
    results = []
    for sid, name, phone, proxy_str, is_active, status in sessions:
        proxy = parse_http_proxy(proxy_str) if proxy_str else None
        try:
            client = TelegramClient(name, API_ID, API_HASH, proxy=proxy)
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                results.append(f"Активен: {name} (@{me.username})")
                update_session_status(name, 'active')
                with sessions_lock:
                    if name in sessions_clients:
                        try:
                            await sessions_clients[name].disconnect()
                        except:
                            pass
                    sessions_clients[name] = client
                    refresh_available_clients()
            else:
                results.append(f"НЕ АКТИВЕН: {name}")
                update_session_status(name, 'inactive')
                await client.disconnect()
        except Exception as e:
            results.append(f"Ошибка {name}: {str(e)[:50]}")
            update_session_status(name, 'error')
        await asyncio.sleep(1)
    result_text = "Результаты проверки сессий\n\n" + "\n".join(results)
    bot.send_message(chat_id, result_text, parse_mode='HTML')

def init_sessions():
    sessions = get_all_sessions()
    for sid, name, phone, proxy_str, is_active, status in sessions:
        if status == 'active':
            proxy = parse_http_proxy(proxy_str) if proxy_str else None
            try:
                client = TelegramClient(name, API_ID, API_HASH, proxy=proxy)
                future = asyncio.run_coroutine_threadsafe(init_client(client, name), loop)
                future.result(timeout=30)
            except Exception as e:
                logger.error(f"Ошибка инициализации сессии {name}: {e}")
                update_session_status(name, 'error')
    refresh_available_clients()

async def init_client(client, name):
    await client.connect()
    if await client.is_user_authorized():
        with sessions_lock:
            sessions_clients[name] = client
        logger.info(f"Сессия {name} загружена")
    else:
        await client.disconnect()

@bot.message_handler(func=lambda m: m.text == f"{EMOJI['admin']} АДМИН")
def admin_button(message):
    if message.from_user.id == ADMIN_ID:
        show_admin_panel(message.chat.id)
    else:
        bot.send_message(message.chat.id, "Нет доступа")

@bot.message_handler(func=lambda message: True)
def unknown_command(message):
    logger.warning(f"Неизвестная команда от {message.from_user.id}: {message.text}")

def run_async_loop():
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    init_sessions()
    loop.run_forever()

if __name__ == "__main__":
    print("=" * 60)
    print("БОТ ЗАПУЩЕН")
    print(f"Админ ID: {ADMIN_ID}")
    print("=" * 60)
    threading.Thread(target=run_async_loop, daemon=True).start()
    time.sleep(2)
    bot.infinity_polling(timeout=60)
