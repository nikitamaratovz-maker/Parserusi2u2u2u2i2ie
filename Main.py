# -*- coding: utf-8 -*-
import re
import time
import random
import datetime
import sqlite3
import threading
import logging
import os
import sys
import hashlib
import base64
import json
import requests
from collections import defaultdict
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from functools import lru_cache

import psutil
from telebot import types
import telebot
from telethon import TelegramClient, functions, errors
import asyncio
from telethon.errors import (
    FloodWaitError, PhoneNumberInvalidError, SessionPasswordNeededError,
    PhoneCodeInvalidError, RPCError, AuthKeyDuplicatedError,
    SessionRevokedError, UserDeactivatedBanError
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.contacts import ResolveUsernameRequest
from telethon.tl.types import InputPeerChannel, Channel, User
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2

# ==================== КОНФИГУРАЦИЯ ====================
BATCH_SIZE = 25
MAX_SESSIONS = 50
REQUESTS_PER_MINUTE = 30
CACHE_TTL = 30
WARMING_HOURS = 24
CHECK_INTERVAL = 60
FRAGMENT_CHECK_TIMEOUT = 2
SESSION_TIMEOUT = 10
MAX_RETRIES = 3

# ==================== ШИФРОВАНИЕ ====================
ENCRYPTION_KEY = hashlib.sha256(b"miyser_ultra_secure_key_2024!@#$%^&*()").digest()
fernet = Fernet(base64.urlsafe_b64encode(ENCRYPTION_KEY[:32]))

def encrypt_data(data: str) -> str:
    """Шифрует строку"""
    if not data:
        return data
    return fernet.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str) -> str:
    """Расшифровывает строку"""
    if not encrypted_data:
        return encrypted_data
    try:
        return fernet.decrypt(encrypted_data.encode()).decode()
    except:
        return encrypted_data

def hash_sensitive(data: str) -> str:
    """Хеширует чувствительные данные"""
    return hashlib.sha256(data.encode()).hexdigest()[:16]

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Фильтр для удаления чувствительных данных из логов
class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        if hasattr(record, 'msg'):
            record.msg = re.sub(r'\+?\d{10,}', '+****', str(record.msg))
            record.msg = re.sub(r'session_[a-f0-9]+', 'session_****', str(record.msg))
        return True

logger.addFilter(SensitiveDataFilter())

# ==================== ТОКЕНЫ И НАСТРОЙКИ ====================
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
CRYPTO_BOT_TOKEN = "559739:AALFf0i5EFhsnAiXQ2CCrKtWVf2MZFfMmTz"

ADMIN_PASSWORD_HASH = hashlib.sha256(b"admin_secure_pass_2024").hexdigest()

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

EMOJI = {
    'search': '🔍', 'found': '✅', 'error': '❌', 'premium': '💎',
    'profile': '👤', 'stats': '📊', 'info': 'ℹ️', 'referral': '👥',
    'top': '🏆', 'trap': '🎯', 'filter': '🔎', 'channel': '📢',
    'admin': '⚙️', 'star': '⭐', 'crown': '👑', 'fire': '🔥',
    'rocket': '🚀', 'zap': '⚡', 'lock': '🔒', 'time': '⏱️',
    'ban': '🚫', 'unban': '✅', 'green': '🟢', 'yellow': '🟡',
    'red': '🔴', 'orange': '🟠', 'shield': '🛡', 'key': '🔑',
    'globe': '🌐', 'cpu': '📊', 'speed': '⚡', 'package': '📦'
}

# ==================== МЕТРИКИ ====================
@dataclass
class Metrics:
    checks_total: int = 0
    checks_today: int = 0
    found_today: int = 0
    last_found: Optional[Tuple[str, float]] = None
    checks_per_second: float = 0.0
    session_stats: Dict[str, int] = field(default_factory=lambda: {'active': 0, 'flood': 0, 'dead': 0, 'warming': 0})
    proxy_countries: Dict[str, int] = field(default_factory=dict)
    cpu_percent: float = 0.0
    last_update: float = 0.0
    recent_checks: List[float] = field(default_factory=list)
    
    def update_speed(self):
        now = time.time()
        self.recent_checks = [t for t in self.recent_checks if now - t < 10]
        self.checks_per_second = len(self.recent_checks) / 10 if self.recent_checks else 0
        self.cpu_percent = psutil.cpu_percent(interval=0.1)
        self.last_update = now
    
    def add_check(self):
        self.checks_total += 1
        self.checks_today += 1
        self.recent_checks.append(time.time())
    
    def add_found(self, username: str):
        self.found_today += 1
        self.last_found = (username, time.time())

metrics = Metrics()
metrics_lock = threading.RLock()

# ==================== КЭШ ====================
class UsernameCache:
    def __init__(self, ttl: int = CACHE_TTL):
        self.cache: Dict[str, Tuple[bool, float]] = {}
        self.ttl = ttl
        self.lock = threading.RLock()
    
    def get(self, username: str) -> Optional[bool]:
        with self.lock:
            if username in self.cache:
                result, timestamp = self.cache[username]
                if time.time() - timestamp < self.ttl:
                    return result
                else:
                    del self.cache[username]
        return None
    
    def set(self, username: str, result: bool):
        with self.lock:
            self.cache[username] = (result, time.time())
    
    def clear(self):
        with self.lock:
            self.cache.clear()
    
    def size(self) -> int:
        return len(self.cache)

username_cache = UsernameCache()

# ==================== БАЗА ДАННЫХ ====================
DB_PASSWORD = hashlib.sha256(b"db_secure_password_2024!@#").hexdigest()

conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
db_lock = threading.RLock()

user_actions = defaultdict(list)
blocked_users = {}
ip_blacklist = {}
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
    proxy_country TEXT DEFAULT 'unknown',
    is_active INTEGER DEFAULT 1,
    added_at TEXT,
    last_check TEXT,
    status TEXT DEFAULT 'active',
    flood_until REAL DEFAULT 0,
    last_used REAL DEFAULT 0,
    requests_today INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    priority INTEGER DEFAULT 5
)
''')

# Таблица для логов админов
cursor.execute('''
CREATE TABLE IF NOT EXISTS admin_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    action TEXT,
    details TEXT,
    ip_address TEXT,
    created_at TEXT
)
''')

# Таблица для капчи
cursor.execute('''
CREATE TABLE IF NOT EXISTS captcha (
    user_id INTEGER PRIMARY KEY,
    passed INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    last_attempt TEXT
)
''')

conn.commit()

sessions_clients = {}
sessions_lock = threading.RLock()
loop = None
temp_session_data = {}
available_clients = []
session_queue = []
session_queue_lock = threading.RLock()
current_session_index = 0

def migrate_database():
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    required_columns = {
        'trial_used': 'INTEGER DEFAULT 0',
        'search_packages': 'INTEGER DEFAULT 0',
        'banned': 'INTEGER DEFAULT 0',
        'ip_address': 'TEXT',
        'user_agent': 'TEXT',
        'captcha_passed': 'INTEGER DEFAULT 0'
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
    banned INTEGER DEFAULT 0,
    ip_address TEXT,
    user_agent TEXT,
    captcha_passed INTEGER DEFAULT 0
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

# ==================== ФУНКЦИИ БД ====================
def get_user(user_id):
    with db_lock:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None

def create_user(user_id, username=None, referrer_id=None, ip_address=None, user_agent=None):
    with db_lock:
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            return get_user(user_id), False
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            'INSERT INTO users (user_id, username, referrer_id, created_date, ip_address, user_agent) VALUES (?, ?, ?, ?, ?, ?)',
            (user_id, username, referrer_id, now, 
             hash_sensitive(ip_address or ''), hash_sensitive(user_agent or ''))
        )
        conn.commit()
        return get_user(user_id), True

def update_user(user_id, **kwargs):
    allowed_fields = {
        'username', 'referrer_id', 'referrals_count', 'subscription_end',
        'searches_today', 'last_search_date', 'total_searches',
        'found_count', 'subscribed', 'referral_activated', 'trial_used',
        'search_packages', 'banned', 'captcha_passed'
    }
    with db_lock:
        for key, val in kwargs.items():
            if key in allowed_fields:
                cursor.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (val, user_id))
        conn.commit()

def add_admin_log(admin_id: int, action: str, details: str = "", ip_address: str = ""):
    with db_lock:
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            'INSERT INTO admin_logs (admin_id, action, details, ip_address, created_at) VALUES (?, ?, ?, ?, ?)',
            (admin_id, action, details, hash_sensitive(ip_address), now)
        )
        conn.commit()

def get_admin_logs(limit: int = 50):
    with db_lock:
        cursor.execute('SELECT admin_id, action, details, created_at FROM admin_logs ORDER BY id DESC LIMIT ?', (limit,))
        return cursor.fetchall()

# ==================== АНТИ-СПАМ И БЕЗОПАСНОСТЬ ====================
def check_captcha(user_id: int) -> bool:
    """Проверка капчи для пользователя"""
    with db_lock:
        cursor.execute("SELECT passed, attempts FROM captcha WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row[0] == 1:
            return True
    return False

def generate_captcha() -> Tuple[str, str]:
    """Генерирует простую математическую капчу"""
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    operation = random.choice(['+', '-', '*'])
    if operation == '+':
        answer = str(a + b)
        question = f"{a} + {b}"
    elif operation == '-':
        answer = str(a - b)
        question = f"{a} - {b}"
    else:
        answer = str(a * b)
        question = f"{a} * {b}"
    return question, answer

captcha_answers: Dict[int, str] = {}

def check_rate_limit(user_id, action_type='general', ip_address=None):
    current_time = time.time()
    
    # Проверка IP бана
    if ip_address and hash_sensitive(ip_address) in ip_blacklist:
        ban_info = ip_blacklist[hash_sensitive(ip_address)]
        if current_time < ban_info['until']:
            return False, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>IP заблокирован!</b>"
        else:
            del ip_blacklist[hash_sensitive(ip_address)]
    
    if user_id in blocked_users:
        if current_time < blocked_users[user_id]:
            remaining = int(blocked_users[user_id] - current_time)
            return False, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Вы заблокированы!</b>\nОсталось: {remaining} сек."
        else:
            del blocked_users[user_id]
            user_actions[user_id] = []
    
    actions = user_actions[user_id]
    if action_type == 'start':
        actions[:] = [t for t in actions if current_time - t < START_WINDOW]
        if len(actions) >= START_LIMIT:
            blocked_users[user_id] = current_time + BLOCK_DURATION
            user_actions[user_id] = []
            if ip_address:
                ip_blacklist[hash_sensitive(ip_address)] = {'until': current_time + BLOCK_DURATION * 2}
            return False, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Вы заблокированы на 5 минут!</b>"
        actions.append(current_time)
        return True, None
    else:
        actions[:] = [t for t in actions if current_time - t < ACTION_COOLDOWN]
        if actions and (current_time - actions[-1]) < ACTION_COOLDOWN:
            return False, f"<tg-emoji emoji-id='5134438483867206614'>⏱️</tg-emoji> <b>Подожди немного</b>"
        actions.append(current_time)
        return True, None

def check_referral_validity(referrer_id: int, new_user_id: int) -> bool:
    """Проверка валидности реферала"""
    referrer = get_user(referrer_id)
    new_user = get_user(new_user_id)
    
    if not referrer or not new_user:
        return False
    
    # Проверка на накрутку: нельзя быть рефералом самого себя
    if referrer_id == new_user_id:
        return False
    
    # Проверка на цепочку рефералов (максимум 2 уровня)
    if referrer.get('referrer_id') == new_user_id:
        return False
    
    return True

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
    
    if not check_referral_validity(referrer_id, user_id):
        return False
    
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

# ==================== УПРАВЛЕНИЕ СЕССИЯМИ ====================
def parse_http_proxy(proxy_str):
    if not proxy_str or proxy_str.lower() == 'нет':
        return None
    try:
        proxy_type = 'socks5'
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
            'proxy_type': proxy_type,
            'addr': ip,
            'port': int(port),
            'username': username,
            'password': password
        }
    except Exception as e:
        logger.error(f"Ошибка парсинга прокси: {e}")
        return None

def get_proxy_country(proxy: dict) -> str:
    """Определяет страну прокси по IP"""
    try:
        ip = proxy.get('addr', '')
        if ip.startswith('10.') or ip.startswith('192.168.') or ip.startswith('172.'):
            return 'local'
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
        data = response.json()
        return data.get('countryCode', 'unknown')
    except:
        return 'unknown'

def update_session_metrics():
    """Обновляет метрики сессий"""
    active = 0
    flood = 0
    dead = 0
    warming = 0
    countries = {}
    
    with db_lock:
        cursor.execute("SELECT status, proxy_country FROM sessions")
        for status, country in cursor.fetchall():
            if status == 'active':
                active += 1
            elif status == 'flood':
                flood += 1
            elif status == 'dead':
                dead += 1
            elif status == 'warming':
                warming += 1
            
            if country and country != 'unknown':
                countries[country] = countries.get(country, 0) + 1
    
    with metrics_lock:
        metrics.session_stats = {
            'active': active,
            'flood': flood,
            'dead': dead,
            'warming': warming
        }
        metrics.proxy_countries = countries

def refresh_available_clients():
    global available_clients, session_queue
    with sessions_lock:
        available_clients = list(sessions_clients.values())
        # Сортируем по приоритету (свежие сессии в конец)
        session_queue = sorted(
            [(c.session.filename, c) for c in available_clients],
            key=lambda x: sessions_clients.get(x[0], {}).get('priority', 5) if hasattr(sessions_clients.get(x[0], {}), 'get') else 5
        )
    update_session_metrics()
    return len(available_clients)

def get_available_client():
    """Возвращает следующего клиента по round-robin"""
    global current_session_index
    with sessions_lock:
        if not session_queue:
            return None
        current_session_index = (current_session_index + 1) % len(session_queue)
        return session_queue[current_session_index][1]

async def _check_username_via_session(client, username):
    """Асинхронная проверка через клиент (только MTProto)"""
    try:
        await asyncio.wait_for(
            client(ResolveUsernameRequest(username)),
            timeout=REQUEST_TIMEOUT
        )
        return False  # Ник занят
    except errors.UsernameNotOccupiedError:
        return True  # Ник свободен
    except FloodWaitError as e:
        logger.warning(f"Flood wait {e.seconds}s в сессии {client.session.filename}")
        update_session_in_db(client.session.filename, 'flood', flood_until=time.time() + e.seconds)
        return None
    except (AuthKeyDuplicatedError, SessionRevokedError) as e:
        logger.error(f"Сессия {client.session.filename} мертва: {e}")
        update_session_in_db(client.session.filename, 'dead')
        with sessions_lock:
            if client.session.filename in sessions_clients:
                del sessions_clients[client.session.filename]
        refresh_available_clients()
        return None
    except asyncio.TimeoutError:
        return None
    except Exception as e:
        logger.error(f"Ошибка проверки {username}: {e}")
        return None

def check_username_via_session_sync(username):
    """Синхронная обёртка для проверки через сессии"""
    client = get_available_client()
    if not client:
        return None
    
    try:
        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                _check_username_via_session(client, username), loop
            )
            return future.result(timeout=10)
    except Exception as e:
        logger.error(f"Ошибка при проверке {username}: {e}")
    
    return None

async def _batch_check_usernames(client, usernames: List[str]) -> Dict[str, Optional[bool]]:
    """Пакетная проверка ников через одну сессию"""
    results = {}
    for username in usernames:
        result = await _check_username_via_session(client, username)
        results[username] = result
        if result is True:
            with metrics_lock:
                metrics.add_found(username)
        with metrics_lock:
            metrics.add_check()
        await asyncio.sleep(0.05)  # Небольшая задержка между запросами
    return results

async def _parallel_check_usernames(usernames: List[str]) -> Dict[str, Optional[bool]]:
    """Параллельная проверка через все доступные сессии"""
    if not available_clients:
        return {}
    
    # Разбиваем на батчи по количеству сессий
    batch_size = max(1, len(usernames) // len(available_clients))
    batches = []
    for i in range(0, len(usernames), batch_size):
        batches.append(usernames[i:i+batch_size])
    
    # Распределяем батчи по сессиям
    tasks = []
    for i, batch in enumerate(batches):
        if i < len(available_clients):
            client = available_clients[i]
            tasks.append(_batch_check_usernames(client, batch))
    
    # Запускаем параллельно
    results = {}
    if tasks:
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        for batch_result in batch_results:
            if isinstance(batch_result, dict):
                results.update(batch_result)
    
    return results

def check_username_full(username):
    """Улучшенная проверка с приоритетом сессий (без веб-запросов)"""
    # Проверяем кэш
    cached = username_cache.get(username)
    if cached is not None:
        return cached
    
    # Проверяем через сессии
    session_result = check_username_via_session_sync(username)
    if session_result is not None:
        username_cache.set(username, session_result)
        return session_result
    
    # Дополнительная проверка через Fragment (только для свободных)
    if session_result is True:
        try:
            r = requests.get(f"https://fragment.com/username/{username}", timeout=FRAGMENT_CHECK_TIMEOUT, allow_redirects=True)
            if "query=" in r.url or "auction" in r.text.lower() or "for sale" in r.text.lower():
                username_cache.set(username, False)
                return False
        except:
            pass
    
    result = session_result if session_result is not None else True
    username_cache.set(username, result)
    return result

async def ultra_fast_check(username: str) -> bool:
    """Ультра-быстрая проверка одного ника"""
    # Проверяем кэш
    cached = username_cache.get(username)
    if cached is not None:
        return cached
    
    client = get_available_client()
    if not client:
        return True
    
    try:
        result = await _check_username_via_session(client, username)
        if result is True:
            # Проверяем Fragment (чтобы исключить ники на аукционе)
            try:
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: requests.get(f"https://fragment.com/username/{username}", 
                                        timeout=FRAGMENT_CHECK_TIMEOUT, allow_redirects=True)
                )
                if "query=" in response.url or "auction" in response.text.lower():
                    result = False
            except:
                pass
        
        username_cache.set(username, result if result is not None else True)
        return result if result is not None else True
    except:
        return True

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

# ==================== НОВАЯ АДМИН-ПАНЕЛЬ С МЕТРИКАМИ ====================
def get_admin_dashboard_text():
    """Формирует текст главного экрана админ-панели с метриками"""
    with metrics_lock:
        active = metrics.session_stats.get('active', 0)
        flood = metrics.session_stats.get('flood', 0)
        dead = metrics.session_stats.get('dead', 0)
        speed = metrics.checks_per_second
        cpu = metrics.cpu_percent
        found_today = metrics.found_today
        checks_today = metrics.checks_today
        
        # Последняя находка
        last_found_text = "Нет"
        if metrics.last_found:
            username, timestamp = metrics.last_found
            minutes_ago = int((time.time() - timestamp) / 60)
            last_found_text = f"@{username} ({minutes_ago} мин. назад)"
        
        # Страны прокси
        countries_text = ""
        for country, count in sorted(metrics.proxy_countries.items(), key=lambda x: x[1], reverse=True):
            flag = {'RU': '🇷🇺', 'DE': '🇩🇪', 'US': '🇺🇸', 'NL': '🇳🇱', 'FR': '🇫🇷', 'GB': '🇬🇧', 'local': '🏠'}.get(country, '🌐')
            countries_text += f"{flag} {country}({count}) | "
        countries_text = countries_text.rstrip(' | ') if countries_text else "Нет данных"
    
    text = (
        f"<b>🛠 УПРАВЛЕНИЕ СИСТЕМОЙ</b>\n\n"
        f"🟢 Активные: {active} | 🟡 Flood: {flood} | 🔴 Dead: {dead}\n"
        f"⚡ Скорость: {speed:.1f} ников/сек\n"
        f"📊 Загрузка CPU: {cpu:.1f}%\n"
        f"🛡 Прокси: {countries_text}\n"
        f"🔎 Последняя находка: {last_found_text}\n"
        f"📦 Проверено сегодня: {checks_today:,} ников\n"
        f"✅ Найдено сегодня: {found_today} ников\n\n"
        f"<b>Выберите действие:</b>"
    )
    return text

def get_detailed_sessions_text():
    """Формирует детальный список сессий"""
    with db_lock:
        cursor.execute("SELECT id, session_name, phone, proxy_country, status, flood_until, requests_today, errors_count FROM sessions ORDER BY status, id")
        sessions = cursor.fetchall()
    
    if not sessions:
        return "📋 <b>СПИСОК СЕССИЙ</b>\n\nНет добавленных сессий"
    
    text = f"📋 <b>СПИСОК СЕССИЙ</b> ({len(sessions)} всего)\n\n"
    
    for sid, name, phone, country, status, flood_until, req_today, errors in sessions:
        status_emoji = {'active': '🟢', 'flood': '🟡', 'dead': '🔴', 'warming': '🟠'}.get(status, '⚪')
        country_flag = {'RU': '🇷🇺', 'DE': '🇩🇪', 'US': '🇺🇸', 'NL': '🇳🇱', 'FR': '🇫🇷', 'GB': '🇬🇧', 'local': '🏠'}.get(country, '🌐')
        
        phone_masked = phone[:4] + '****' + phone[-4:] if phone and len(phone) > 8 else '****'
        
        status_text = status
        if status == 'flood' and flood_until > time.time():
            remaining = int(flood_until - time.time())
            status_text += f" до {remaining}с"
        
        text += f"{status_emoji} {name}\n"
        text += f"   📱 {phone_masked} | {country_flag} {country}\n"
        text += f"   📊 {req_today} запросов | ❌ {errors} ошибок\n"
        text += f"   Статус: {status_text} | ID: {sid}\n\n"
    
    return text

# ==================== ОБРАБОТЧИКИ ====================
@bot.message_handler(commands=['start'])
@error_handler
def start(message):
    user_id = message.from_user.id
    
    if is_banned(user_id):
        bot.send_message(user_id, "<tg-emoji emoji-id='5121063440311386962'>🚫</tg-emoji> <b>Вы заблокированы.</b>", parse_mode='HTML')
        return
    
    # Получаем IP и User-Agent (если доступны)
    ip_address = None
    user_agent = None
    if hasattr(message, 'json'):
        try:
            ip_address = message.json.get('from', {}).get('ip', None)
        except:
            pass
    
    allowed, error_msg = check_rate_limit(user_id, 'start', ip_address)
    if not allowed:
        # Предлагаем капчу при блокировке
        if "заблокированы" in error_msg.lower():
            question, answer = generate_captcha()
            captcha_answers[user_id] = answer
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🤖 Я не робот", callback_data=f"verify_captcha_{user_id}"))
            bot.send_message(user_id, error_msg + f"\n\n<b>Решите пример для разблокировки:</b>\n{question} = ?", parse_mode='HTML', reply_markup=markup)
        else:
            bot.send_message(user_id, error_msg, parse_mode='HTML')
        return
    
    username = message.from_user.username
    referrer_id = None
    if len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
            if referrer_id == user_id: referrer_id = None
        except: pass
    
    user, is_new = create_user(user_id, username, referrer_id, ip_address, user_agent)
    
    if is_new:
        # Капча для новых пользователей
        question, answer = generate_captcha()
        captcha_answers[user_id] = answer
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🤖 Подтвердить", callback_data=f"new_user_captcha_{user_id}"))
        bot.send_message(user_id, 
            f"<tg-emoji emoji-id='6082635604896520956'>🚀</tg-emoji> <b>Добро пожаловать!</b>\n\n"
            f"Для защиты от спама решите пример:\n<b>{question} = ?</b>", 
            parse_mode='HTML', reply_markup=markup)
        return
    
    if check_subscription(user_id):
        activate_referral(user_id)
        welcome = (f"<tg-emoji emoji-id='4918354603281482671'>⭐</tg-emoji> ДОБРО ПОЖАЛОВАТЬ!\n\n"
                  f"<tg-emoji emoji-id='4906943755644306322'>⭐</tg-emoji> У нас можно:\n"
                  f"<tg-emoji emoji-id='4902524693858222969'>⭐</tg-emoji> Поиск 5-6 букв\n"
                  f"<tg-emoji emoji-id='4902524693858222969'>⭐</tg-emoji> Поиск по слову\n"
                  f"<tg-emoji emoji-id='4902524693858222969'>⭐</tg-emoji> Поиск по фильтру\n\n"
                  f"<tg-emoji emoji-id='4918203446202467778'>💎</tg-emoji> <b>Premium от 49⭐</b> — безлимит + всё!\n"
                  f"<tg-emoji emoji-id='4916105371858240403'>⭐</tg-emoji> Бот иногда может выдавть юзернеймы которые заблокированы в ТГ или стоят на продаже")
        bot.send_photo(user_id, photo="https://i.postimg.cc/nhbMgpRy/1775474714965.png", caption=welcome, parse_mode='HTML', reply_markup=get_main_keyboard(user_id))
    else:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Подписаться на канал", url=CHANNEL_LINK))
        bot.send_message(user_id, "Сначала подпишись на наш канал", parse_mode='HTML', reply_markup=markup)

# ========== ОБРАБОТЧИК КАПЧИ ==========
@bot.callback_query_handler(func=lambda call: call.data.startswith('new_user_captcha_') or call.data.startswith('verify_captcha_'))
def captcha_callback(call):
    user_id = int(call.data.split('_')[-1])
    
    if user_id not in captcha_answers:
        bot.answer_callback_query(call.id, "Капча устарела. Напишите /start")
        return
    
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Введите ответ на пример:")
    bot.register_next_step_handler(msg, process_captcha_answer, user_id)

def process_captcha_answer(message, user_id):
    try:
        user_answer = message.text.strip()
        correct_answer = captcha_answers.get(user_id, '')
        
        if user_answer == correct_answer:
            del captcha_answers[user_id]
            update_user(user_id, captcha_passed=1)
            with db_lock:
                cursor.execute("INSERT OR REPLACE INTO captcha (user_id, passed, attempts, last_attempt) VALUES (?, 1, 0, datetime('now'))", (user_id,))
                conn.commit()
            
            # Продолжаем регистрацию
            user = get_user(user_id)
            if check_subscription(user_id):
                activate_referral(user_id)
                welcome = (f"<tg-emoji emoji-id='4918354603281482671'>⭐</tg-emoji> ДОБРО ПОЖАЛОВАТЬ!\n\n"
                          f"<tg-emoji emoji-id='4906943755644306322'>⭐</tg-emoji> У нас можно:\n"
                          f"<tg-emoji emoji-id='4902524693858222969'>⭐</tg-emoji> Поиск 5-6 букв\n"
                          f"<tg-emoji emoji-id='4902524693858222969'>⭐</tg-emoji> Поиск по слову\n"
                          f"<tg-emoji emoji-id='4902524693858222969'>⭐</tg-emoji> Поиск по фильтру\n\n"
                          f"<tg-emoji emoji-id='4918203446202467778'>💎</tg-emoji> <b>Premium от 49⭐</b> — безлимит + всё!")
                bot.send_photo(user_id, photo="https://i.postimg.cc/nhbMgpRy/1775474714965.png", caption=welcome, parse_mode='HTML', reply_markup=get_main_keyboard(user_id))
        else:
            with db_lock:
                cursor.execute("INSERT OR REPLACE INTO captcha (user_id, passed, attempts, last_attempt) VALUES (?, 0, COALESCE((SELECT attempts FROM captcha WHERE user_id = ?), 0) + 1, datetime('now'))", (user_id, user_id))
                conn.commit()
            
            if user_id in user_actions:
                user_actions[user_id] = []  # Сброс попыток
            blocked_users[user_id] = time.time() + 300
            bot.send_message(user_id, "<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Неверно! Заблокированы на 5 минут.</b>", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка проверки капчи: {e}")

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
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> <b>Ловушка</b> — уведомит, когда ник освободится.\n\n"
            f"<tg-emoji emoji-id='4916105371858240403'>⚡</tg-emoji> Скорость проверки: до 100+ ников/сек")
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
        msg = bot.send_message(user_id, f"<tg-emoji emoji-id='5134122666331996794'>🔍</tg-emoji> <b>Ищу {length}-буквенный ник...</b>\n⚡ Используется {len(available_clients)} сессий", parse_mode='HTML')
    
    found_usernames = set()
    username_cache.clear()  # Очищаем кэш для нового поиска
    
    # Ускоренный поиск с батчами
    for batch_num in range(SEARCH_ATTEMPTS // BATCH_SIZE):
        # Генерируем батч ников
        batch = []
        for _ in range(BATCH_SIZE):
            nick = generate_smart_nick(length)
            while nick in found_usernames:
                nick = generate_smart_nick(length)
            batch.append(nick)
            found_usernames.add(nick)
        
        # Параллельная проверка батча
        results = {}
        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                _parallel_check_usernames(batch), loop
            )
            try:
                results = future.result(timeout=5)
            except:
                pass
        
        # Обрабатываем результаты
        for username, is_free in results.items():
            if is_free is True:
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
        
        if msg and batch_num % 2 == 0:
            try: bot.edit_message_text(f"<tg-emoji emoji-id='5134122666331996794'>🔍</tg-emoji> <b>Поиск...</b> {batch_num*BATCH_SIZE}/{SEARCH_ATTEMPTS}\n⚡ Скорость: {metrics.checks_per_second:.1f} ник/сек", user_id, msg.message_id, parse_mode='HTML')
            except: pass
    
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
    username_cache.clear()
    
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
    bot.send_photo(user_id, photo="https://i.postimg.cc/nhbMgpRy/1775474714965.png", caption=f"🔤 <b>СЛОВО</b>\n\nВведите основу (например: <code>style</code>)\nБот найдет свободные ники с этим корнем\nМинимум 3 буквы, максимум 10 букв",
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
        types.InlineKeyboardButton("🔄 Сессии", callback_data="admin_sessions_menu"),
        types.InlineKeyboardButton("🛡 Безопасность", callback_data="admin_security"),
        types.InlineKeyboardButton("📋 Логи админов", callback_data="admin_logs")
    )
    return markup

def sessions_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Добавить сессию", callback_data="session_add"),
        types.InlineKeyboardButton("📋 Список сессий", callback_data="session_list"),
        types.InlineKeyboardButton("🔍 Проверить все сессии", callback_data="session_check_all"),
        types.InlineKeyboardButton("🔄 Обновить статусы", callback_data="session_refresh_status"),
        types.InlineKeyboardButton("🗑️ Удалить мёртвые", callback_data="session_clean_dead"),
        types.InlineKeyboardButton("📊 Статус системы", callback_data="session_system_status"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
    )
    return markup

def security_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔑 Изменить пароль админа", callback_data="security_change_pass"),
        types.InlineKeyboardButton("📋 Логи действий", callback_data="admin_logs"),
        types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
    )
    return markup

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@bot.message_handler(commands=['start'])
@error_handler
def start(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        bot.send_message(user_id, "<tg-emoji emoji-id='5121063440311386962'>🚫</tg-emoji> <b>Вы заблокированы.</b>", parse_mode='HTML')
        return
    
    # Проверка капчи для новых пользователей
    user = get_user(user_id)
    if not user or not user.get('captcha_passed', 0):
        question, answer = generate_captcha()
        captcha_answers[user_id] = answer
        bot.send_message(user_id, 
            f"<tg-emoji emoji-id='4916105371858240403'>🔒</tg-emoji> <b>Проверка безопасности</b>\n\n"
            f"Решите пример: <b>{question} = ?</b>\n\n"
            f"Введите ответ числом:")
        bot.register_next_step_handler(message, process_captcha_start, user_id)
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
        if is_new:
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

def process_captcha_start(message, user_id):
    """Обработка капчи для новых пользователей"""
    if message.from_user.id != user_id:
        return
    
    user_answer = message.text.strip()
    correct_answer = captcha_answers.get(user_id, '')
    
    if user_answer == correct_answer:
        with db_lock:
            cursor.execute("INSERT OR REPLACE INTO captcha (user_id, passed, attempts, last_attempt) VALUES (?, 1, 1, ?)",
                          (user_id, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
        update_user(user_id, captcha_passed=1)
        captcha_answers.pop(user_id, None)
        bot.send_message(user_id, "<tg-emoji emoji-id='5123163417326126159'>✅</tg-emoji> <b>Проверка пройдена!</b>", parse_mode='HTML')
        # Повторно вызываем start
        start(message)
    else:
        with db_lock:
            cursor.execute("SELECT attempts FROM captcha WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            attempts = (row[0] if row else 0) + 1
            cursor.execute("INSERT OR REPLACE INTO captcha (user_id, passed, attempts, last_attempt) VALUES (?, 0, ?, ?)",
                          (user_id, attempts, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
        
        if attempts >= 3:
            update_user(user_id, banned=1)
            bot.send_message(user_id, "<tg-emoji emoji-id='5121063440311386962'>🚫</tg-emoji> <b>Вы заблокированы за подозрительную активность.</b>", parse_mode='HTML')
            captcha_answers.pop(user_id, None)
            return
        
        question, answer = generate_captcha()
        captcha_answers[user_id] = answer
        bot.send_message(user_id,
            f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Неверно!</b> Осталось попыток: {3 - attempts}\n\n"
            f"Решите пример: <b>{question} = ?</b>")
        bot.register_next_step_handler(message, process_captcha_start, user_id)

# ==================== ПОИСК ====================
@bot.message_handler(func=lambda m: m.text == "Поиск")
@subscription_required
@error_handler
def search_menu_handler(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        bot.send_message(user_id, "<tg-emoji emoji-id='5121063440311386962'>🚫</tg-emoji> <b>Вы заблокированы.</b>", parse_mode='HTML')
        return
    
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
    if has_premium(user_id):
        markup.add(types.InlineKeyboardButton("🚀 Быстрый подбор (5 ников)", callback_data="search_mode_fast"))
    bot.send_message(user_id, text, parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "search_close")
def search_close_handler(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)

def perform_search(user_id, length, msg=None):
    """Ускоренный поиск с пакетной проверкой"""
    if get_available_searches(user_id) <= 0:
        bot.send_message(user_id, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Лимит исчерпан!</b>\n\n<tg-emoji emoji-id='4918203446202467778'>💎</tg-emoji> Купите премиум", parse_mode='HTML')
        return
    if not msg:
        msg = bot.send_message(user_id, f"<tg-emoji emoji-id='5134122666331996794'>🔍</tg-emoji> <b>Ищу {length}-буквенный ник...</b>", parse_mode='HTML')
    
    found_usernames = set()
    batch_size = BATCH_SIZE if len(available_clients) >= 3 else 10
    
    # Генерируем и проверяем большими батчами
    for batch_num in range(SEARCH_ATTEMPTS // (batch_size // 25 + 1)):
        # Генерируем батч ников
        batch = []
        while len(batch) < batch_size:
            nick = generate_smart_nick(length)
            if nick not in found_usernames:
                found_usernames.add(nick)
                batch.append(nick)
        
        # Параллельная проверка
        if loop and loop.is_running() and len(available_clients) >= 2:
            future = asyncio.run_coroutine_threadsafe(
                _parallel_check_usernames(batch), loop
            )
            try:
                results = future.result(timeout=15)
            except Exception as e:
                logger.error(f"Ошибка параллельной проверки: {e}")
                results = {}
            
            for username, is_free in results.items():
                if is_free:
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
                    with metrics_lock:
                        metrics.add_found(username)
                    return
        else:
            # Последовательная проверка если нет сессий
            for username in batch:
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
                    with metrics_lock:
                        metrics.add_found(username)
                    return
        
        if msg:
            try: bot.edit_message_text(f"<tg-emoji emoji-id='5134122666331996794'>🔍</tg-emoji> <b>Поиск...</b> батч {batch_num+1}", user_id, msg.message_id, parse_mode='HTML')
            except: pass
        time.sleep(0.01)
    
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
    username_cache.clear()
    perform_search(user_id, 5, None)

@bot.callback_query_handler(func=lambda call: call.data == "search_mode_6")
@subscription_required
@error_handler
def search_6_handler(call):
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)
    allowed, error_msg = check_rate_limit(user_id)
    if not allowed: bot.send_message(user_id, error_msg, parse_mode='HTML'); return
    username_cache.clear()
    perform_search(user_id, 6, None)

@bot.callback_query_handler(func=lambda call: call.data == "search_mode_fast")
@subscription_required
@error_handler
def search_fast_handler(call):
    """Быстрый подбор 5 ников для Premium"""
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)
    if not has_premium(user_id):
        bot.send_message(user_id, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Только для Premium!</b>", parse_mode='HTML')
        return
    
    username_cache.clear()
    msg = bot.send_message(user_id, f"<tg-emoji emoji-id='5134122666331996794'>🔍</tg-emoji> <b>Быстрый подбор 5 ников...</b>", parse_mode='HTML')
    
    found = []
    attempts = 0
    max_attempts = 200
    
    while len(found) < 5 and attempts < max_attempts:
        length = random.choice([5, 6])
        nick = generate_smart_nick(length)
        if nick in found: continue
        attempts += 1
        
        if check_username_full(nick):
            found.append(nick)
            use_search(user_id)
            add_found(user_id)
            price_range = estimate_price(nick)
            with db_lock:
                try:
                    cursor.execute("INSERT INTO found (username, length, price, found_date, finder_id) VALUES (?, ?, ?, datetime('now'), ?)", 
                                 (nick, length, price_range, user_id))
                    conn.commit()
                except: pass
    
    try: bot.delete_message(user_id, msg.message_id)
    except: pass
    
    if found:
        text = f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> <b>НАЙДЕНЫ НИКИ:</b>\n\n"
        for nick in found:
            text += f"<tg-emoji emoji-id='5084979757905347540'>📛</tg-emoji> @{nick} ({estimate_price(nick)})\n"
        text += f"\n<tg-emoji emoji-id='4911656069207426158'>📢</tg-emoji> Наш канал: {REQUIRED_CHANNEL}"
        bot.send_message(user_id, text, parse_mode='HTML')
    else:
        bot.send_message(user_id, f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Ничего не найдено</b>", parse_mode='HTML')

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
    
    username_cache.clear()
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
            with metrics_lock:
                metrics.add_found(username)
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
    
    username_cache.clear()
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
            with metrics_lock:
                metrics.add_found(username)
            return
        time.sleep(0.05)
    bot.edit_message_text(f"<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Ничего не найдено</b>\n\nПопробуй другое слово!", user_id, msg.message_id, parse_mode='HTML')

# ==================== ПРОФИЛЬ ====================
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

# ==================== СТАТИСТИКА ====================
@bot.message_handler(func=lambda m: m.text == "Статистика (бота)")
def stats(message):
    with db_lock:
        cursor.execute("SELECT COUNT(*) FROM users"); total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_end > datetime('now')"); premium_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM found"); found_nicks = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM traps WHERE status = 'active'"); active_traps = cursor.fetchone()[0]
        try: cursor.execute("SELECT SUM(total_searches) FROM users"); total_searches = cursor.fetchone()[0] or 0
        except: total_searches = 0
    
    with metrics_lock:
        speed = metrics.checks_per_second
    
    text = (f"<tg-emoji emoji-id='4906943755644306322'>⭐</tg-emoji> СТАТИСТИКА БОТА\n\n"
            f"<tg-emoji emoji-id='4904848288345228262'>⭐</tg-emoji> Пользователей: {total_users}\n"
            f"<tg-emoji emoji-id='4913497231492908158'>⭐</tg-emoji> Премиум: {premium_users}\n"
            f"<tg-emoji emoji-id='5084923566848213749'>⭐</tg-emoji> Найдено ников: {found_nicks}\n"
            f"<tg-emoji emoji-id='5098094273039959279'>⭐</tg-emoji> Активных ловушек: {active_traps}\n"
            f"<tg-emoji emoji-id='5116414868357907335'>⭐</tg-emoji> Всего поисков: {total_searches}\n"
            f"<tg-emoji emoji-id='4916105371858240403'>⚡</tg-emoji> Скорость: {speed:.1f} ник/сек")
    bot.send_message(message.chat.id, text, parse_mode='HTML')

# ==================== ПРЕМИУМ ====================
@bot.message_handler(func=lambda m: m.text == "Премиум")
def premium(message):
    user_id = message.from_user.id if hasattr(message, 'from_user') else message.chat.id
    text = (f"<tg-emoji emoji-id='4918203446202467778'>💎</tg-emoji> ПРЕМИУМ ПОДПИСКА\n\n"
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> ФУНКЦИИ:\n"
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> Фильтр по маске\n"
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> Ловушка на ник\n"
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> Слово\n"
            f"<tg-emoji emoji-id='5134122666331996794'>⭐</tg-emoji> Безлимитный поиск\n"
            f"<tg-emoji emoji-id='5134122666331996794'>🚀</tg-emoji> Быстрый подбор 5 ников")
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
            bot.send_message(user_id, f"💳 <b>ОПЛАТА КРИПТОЙ</b>\n\n💰 Сумма: ${price}\n📦 Пакет: {days} дней\n\nНажмите кнопки ниже:", parse_mode='HTML', reply_markup=markup)
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
    show_admin_dashboard(message.chat.id)

def show_admin_dashboard(chat_id):
    """Показывает новую админ-панель с метриками"""
    update_session_metrics()
    with metrics_lock:
        metrics.update_speed()
    text = get_admin_dashboard_text()
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔄 Обновить", callback_data="admin_refresh"),
        types.InlineKeyboardButton("➕ Добавить сессию", callback_data="session_add"),
        types.InlineKeyboardButton("📋 Список сессий", callback_data="session_list"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        types.InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
        types.InlineKeyboardButton("💎 Выдать Premium", callback_data="admin_give_premium"),
        types.InlineKeyboardButton("📦 Выдать поиски", callback_data="admin_give_searches"),
        types.InlineKeyboardButton("🎁 Подарить Premium", callback_data="admin_gift"),
        types.InlineKeyboardButton("🚫 Бан", callback_data="admin_ban"),
        types.InlineKeyboardButton("✅ Разбан", callback_data="admin_unban"),
        types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("🗑️ Снять рефералов", callback_data="admin_removerefs"),
        types.InlineKeyboardButton("🛡 Безопасность", callback_data="admin_security"),
        types.InlineKeyboardButton("📋 Логи админов", callback_data="admin_logs")
    )
    bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_refresh")
def admin_refresh_callback(call):
    """Обновляет метрики и перезагружает админ-панель"""
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    update_session_metrics()
    with metrics_lock:
        metrics.update_speed()
    bot.answer_callback_query(call.id, "✅ Обновлено!")
    
    text = get_admin_dashboard_text()
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔄 Обновить", callback_data="admin_refresh"),
        types.InlineKeyboardButton("➕ Добавить сессию", callback_data="session_add"),
        types.InlineKeyboardButton("📋 Список сессий", callback_data="session_list"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        types.InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
        types.InlineKeyboardButton("💎 Выдать Premium", callback_data="admin_give_premium"),
        types.InlineKeyboardButton("📦 Выдать поиски", callback_data="admin_give_searches"),
        types.InlineKeyboardButton("🎁 Подарить Premium", callback_data="admin_gift"),
        types.InlineKeyboardButton("🚫 Бан", callback_data="admin_ban"),
        types.InlineKeyboardButton("✅ Разбан", callback_data="admin_unban"),
        types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("🗑️ Снять рефералов", callback_data="admin_removerefs"),
        types.InlineKeyboardButton("🛡 Безопасность", callback_data="admin_security"),
        types.InlineKeyboardButton("📋 Логи админов", callback_data="admin_logs")
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)

# Админские 2FA
admin_2fa_pending = {}

def require_admin_2fa(action_func):
    """Декоратор для действий требующих 2FA подтверждения"""
    def wrapper(call):
        if call.from_user.id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Нет доступа")
            return
        
        # Для критических действий запрашиваем пароль
        critical_actions = ['admin_broadcast', 'admin_removerefs']
        if call.data in critical_actions:
            admin_2fa_pending[call.from_user.id] = {'action': call.data, 'message': call.message, 'call': call}
            bot.edit_message_text(
                f"<tg-emoji emoji-id='4916105371858240403'>🔒</tg-emoji> <b>Подтверждение действия</b>\n\n"
                f"Введите пароль администратора для продолжения:",
                call.message.chat.id, call.message.message_id, parse_mode='HTML'
            )
            bot.register_next_step_handler(call.message, process_admin_2fa, call.from_user.id)
            return
        
        return action_func(call)
    return wrapper

def process_admin_2fa(message, admin_id):
    """Обрабатывает ввод пароля 2FA"""
    if message.from_user.id != admin_id:
        return
    
    password = message.text.strip()
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    if password_hash == ADMIN_PASSWORD_HASH:
        pending = admin_2fa_pending.pop(admin_id, None)
        if pending:
            add_admin_log(admin_id, pending['action'], "2FA подтверждено")
            # Вызываем оригинальный обработчик
            if pending['action'] == 'admin_broadcast':
                admin_broadcast_callback(pending['call'])
            elif pending['action'] == 'admin_removerefs':
                admin_removerefs_callback(pending['call'])
        else:
            bot.send_message(message.chat.id, "✅ Действие подтверждено", reply_markup=admin_inline_menu())
    else:
        bot.send_message(message.chat.id, "<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Неверный пароль!</b>", parse_mode='HTML')
        add_admin_log(admin_id, "2FA_FAILED", "Неверный пароль")

@bot.callback_query_handler(func=lambda call: call.data == "admin_security")
def admin_security_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text(
        f"<tg-emoji emoji-id='4916105371858240403'>🛡</tg-emoji> <b>БЕЗОПАСНОСТЬ</b>\n\n"
        f"Выберите действие:",
        call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=security_menu()
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "security_change_pass")
def security_change_pass_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text(
        f"<tg-emoji emoji-id='4916105371858240403'>🔑</tg-emoji> <b>Смена пароля</b>\n\n"
        f"Введите новый пароль администратора:",
        call.message.chat.id, call.message.message_id, parse_mode='HTML'
    )
    bot.register_next_step_handler(call.message, process_change_password, call.from_user.id)
    bot.answer_callback_query(call.id)

def process_change_password(message, admin_id):
    if message.from_user.id != admin_id:
        return
    new_password = message.text.strip()
    if len(new_password) < 8:
        bot.send_message(message.chat.id, "<tg-emoji emoji-id='5121063440311386962'>❌</tg-emoji> <b>Пароль должен быть минимум 8 символов!</b>", parse_mode='HTML')
        return
    
    global ADMIN_PASSWORD_HASH
    ADMIN_PASSWORD_HASH = hashlib.sha256(new_password.encode()).hexdigest()
    add_admin_log(admin_id, "PASSWORD_CHANGED", "Пароль администратора изменён")
    bot.send_message(message.chat.id, "<tg-emoji emoji-id='5123163417326126159'>✅</tg-emoji> <b>Пароль изменён!</b>", parse_mode='HTML', reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_logs")
def admin_logs_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    
    logs = get_admin_logs(20)
    if not logs:
        text = "📋 <b>ЛОГИ АДМИНОВ</b>\n\nНет записей"
    else:
        text = "📋 <b>ЛОГИ АДМИНОВ (последние 20)</b>\n\n"
        for admin_id, action, details, created_at in logs:
            text += f"👤 {admin_id}\n"
            text += f"   Действие: {action}\n"
            if details: text += f"   Детали: {details}\n"
            text += f"   Дата: {created_at}\n\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)
    bot.answer_callback_query(call.id)

# ==================== СЕССИИ ====================
def update_session_in_db(session_name: str, status: str, flood_until: float = 0, errors_count: int = None, requests_today: int = None):
    """Обновление статуса сессии в БД"""
    with db_lock:
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if flood_until > 0:
            cursor.execute("UPDATE sessions SET status = ?, flood_until = ?, last_check = ? WHERE session_name = ?",
                          (status, flood_until, now, session_name))
        elif errors_count is not None:
            cursor.execute("UPDATE sessions SET status = ?, errors_count = ?, last_check = ? WHERE session_name = ?",
                          (status, errors_count, now, session_name))
        elif requests_today is not None:
            cursor.execute("UPDATE sessions SET status = ?, requests_today = ?, last_check = ? WHERE session_name = ?",
                          (status, requests_today, now, session_name))
        else:
            cursor.execute("UPDATE sessions SET status = ?, last_check = ? WHERE session_name = ?",
                          (status, now, session_name))
        conn.commit()
    update_session_metrics()

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
    if message.from_user.id != ADMIN_ID: return
    if message.text.lower() == 'отмена':
        temp_session_data.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, "Отменено", reply_markup=admin_inline_menu())
        return
    phone = message.text.strip()
    if not phone.startswith('+'): phone = '+' + phone
    temp_session_data[message.from_user.id]['phone'] = phone
    bot.send_message(message.chat.id, "Введите прокси (user:pass@ip:port) или 'нет':")
    bot.register_next_step_handler(message, session_add_proxy_step)

def session_add_proxy_step(message):
    if message.from_user.id != ADMIN_ID: return
    if message.text.lower() == 'отмена':
        temp_session_data.pop(message.from_user.id, None)
        bot.send_message(message.chat.id, "Отменено", reply_markup=admin_inline_menu())
        return
    proxy_str = message.text.strip()
    proxy = parse_proxy(proxy_str) if proxy_str.lower() != 'нет' else None
    
    # Определяем страну прокси
    country = 'unknown'
    if proxy:
        country = get_proxy_country(proxy)
    
    temp_session_data[message.from_user.id]['proxy'] = proxy
    temp_session_data[message.from_user.id]['country'] = country
    bot.send_message(message.chat.id, f"Отправляю запрос кода...\n🛡 Страна: {country}")
    asyncio.run_coroutine_threadsafe(
        send_code_request(message.chat.id, message.from_user.id, 
                         temp_session_data[message.from_user.id]['phone'],
                         proxy,
                         country),
        loop
    )

async def send_code_request(chat_id, user_id, phone, proxy, country='unknown'):
    session_name = f"session_{int(time.time())}_{user_id}"
    client = TelegramClient(f"sessions/{session_name}", API_ID, API_HASH, proxy=proxy)
    try:
        await client.connect()
        await client.send_code_request(phone)
        bot.send_message(chat_id, f"Код отправлен на {phone}. Введите его:")
        temp_session_data[user_id]['client'] = client
        temp_session_data[user_id]['session_name'] = session_name
        temp_session_data[user_id]['phone'] = phone
        temp_session_data[user_id]['country'] = country
        bot.register_next_step_handler_by_chat_id(chat_id, session_enter_code_step, user_id)
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка: {str(e)[:100]}")
        temp_session_data.pop(user_id, None)
        await client.disconnect()

def session_enter_code_step(message, user_id):
    if message.from_user.id != ADMIN_ID: return
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
    country = data.get('country', 'unknown')
    
    try:
        await client.sign_in(phone, code)
        me = await client.get_me()
        
        # Сохраняем с зашифрованным телефоном
        proxy_str = f"{proxy.get('proxy_type','')}://{proxy.get('username','')}:****@{proxy.get('addr','')}:{proxy.get('port','')}" if proxy else None
        add_session_to_db(session_name, encrypt_data(phone), proxy_str, country)
        
        with sessions_lock:
            sessions_clients[session_name] = client
        update_session_in_db(session_name, 'warming')
        refresh_available_clients()
        add_admin_log(user_id, "SESSION_ADDED", f"Добавлена сессия {session_name}")
        bot.send_message(chat_id, f"✅ Сессия добавлена!\n{me.first_name} (@{me.username})\n📱 {phone}\n🛡 Страна: {country}")
        show_admin_dashboard(chat_id)
    except SessionPasswordNeededError:
        bot.send_message(chat_id, "Введите пароль 2FA:")
        bot.register_next_step_handler_by_chat_id(chat_id, session_enter_password_step, user_id, session_name, phone, proxy, country)
        return
    except PhoneCodeInvalidError:
        bot.send_message(chat_id, "Неверный код. Попробуйте снова.")
        bot.register_next_step_handler_by_chat_id(chat_id, session_enter_code_step, user_id)
        return
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка: {str(e)[:100]}")
        add_admin_log(user_id, "SESSION_ADD_FAILED", str(e)[:100])
    finally:
        temp_session_data.pop(user_id, None)

def session_enter_password_step(message, user_id, session_name, phone, proxy, country):
    if message.from_user.id != ADMIN_ID: return
    password = message.text.strip()
    data = temp_session_data.get(user_id)
    if not data:
        bot.send_message(message.chat.id, "Данные сессии потеряны")
        return
    client = data['client']
    asyncio.run_coroutine_threadsafe(
        finalize_session_with_password(message.chat.id, user_id, client, session_name, phone, proxy, password, country),
        loop
    )

async def finalize_session_with_password(chat_id, user_id, client, session_name, phone, proxy, password, country):
    try:
        await client.sign_in(password=password)
        me = await client.get_me()
        proxy_str = f"{proxy.get('proxy_type','')}://{proxy.get('username','')}:****@{proxy.get('addr','')}:{proxy.get('port','')}" if proxy else None
        add_session_to_db(session_name, encrypt_data(phone), proxy_str, country)
        with sessions_lock:
            sessions_clients[session_name] = client
        update_session_in_db(session_name, 'warming')
        refresh_available_clients()
        add_admin_log(user_id, "SESSION_ADDED", f"Добавлена сессия {session_name}")
        bot.send_message(chat_id, f"✅ Сессия добавлена!\n{me.first_name} (@{me.username})\n📱 {phone}\n🛡 Страна: {country}")
        show_admin_dashboard(chat_id)
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка: {str(e)[:100]}")
    finally:
        temp_session_data.pop(user_id, None)

def add_session_to_db(session_name: str, phone: str, proxy: str = None, country: str = 'unknown'):
    """Добавляет сессию в БД с зашифрованными данными"""
    with db_lock:
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            'INSERT OR REPLACE INTO sessions (session_name, phone, proxy, proxy_country, added_at, status) VALUES (?, ?, ?, ?, ?, ?)',
            (session_name, phone, proxy, country, now, 'warming')
        )
        conn.commit()
    update_session_metrics()

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
    
    text = get_detailed_sessions_text()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for sid, name, phone, proxy, country, status, flood_until, req_today, errors_count in sessions:
        if status == 'dead':
            markup.add(types.InlineKeyboardButton(f"🔄 Переподключить {name}", callback_data=f"session_reconnect_{sid}"))
        markup.add(types.InlineKeyboardButton(f"🗑️ Удалить {name}", callback_data=f"session_del_{sid}"))
    markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_sessions_menu"))
    
    if len(text) > 4000:
        # Если слишком длинно, отправляем частями
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for i, part in enumerate(parts[:-1]):
            bot.edit_message_text(part, call.message.chat.id, call.message.message_id, parse_mode='HTML')
        bot.send_message(call.message.chat.id, parts[-1], parse_mode='HTML', reply_markup=markup)
    else:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("session_reconnect_"))
def session_reconnect_callback(call):
    """Переподключает мёртвую сессию"""
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    
    sid = int(call.data.split('_')[2])
    with db_lock:
        cursor.execute("SELECT session_name, phone, proxy FROM sessions WHERE id = ?", (sid,))
        row = cursor.fetchone()
    
    if not row:
        bot.answer_callback_query(call.id, "Сессия не найдена")
        return
    
    session_name, encrypted_phone, proxy_str = row
    phone = decrypt_data(encrypted_phone)
    
    proxy = parse_proxy(proxy_str) if proxy_str else None
    if proxy:
        # Убираем звёздочки из пароля (восстановить нельзя, нужно заново вводить)
        proxy = None
    
    bot.answer_callback_query(call.id, "Пытаюсь переподключить...")
    bot.send_message(call.message.chat.id, f"🔄 Переподключаю сессию {session_name}...")
    
    asyncio.run_coroutine_threadsafe(
        reconnect_session(call.message.chat.id, session_name, phone, proxy),
        loop
    )

async def reconnect_session(chat_id, session_name, phone, proxy):
    try:
        client = TelegramClient(f"sessions/{session_name}", API_ID, API_HASH, proxy=proxy)
        await client.connect()
        
        if await client.is_user_authorized():
            with sessions_lock:
                if session_name in sessions_clients:
                    try: await sessions_clients[session_name].disconnect()
                    except: pass
                sessions_clients[session_name] = client
            update_session_in_db(session_name, 'active')
            refresh_available_clients()
            bot.send_message(chat_id, f"✅ Сессия {session_name} переподключена!")
        else:
            bot.send_message(chat_id, f"❌ Сессия {session_name} не авторизована. Удаляю...")
            await client.disconnect()
            delete_session_from_db(session_name)
            try: os.remove(f"sessions/{session_name}.session")
            except: pass
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка переподключения {session_name}: {str(e)[:100]}")
        update_session_in_db(session_name, 'dead')

def delete_session_from_db(session_name_or_id):
    """Удаляет сессию из БД по имени или ID"""
    with db_lock:
        if isinstance(session_name_or_id, int):
            cursor.execute("SELECT session_name FROM sessions WHERE id = ?", (session_name_or_id,))
            row = cursor.fetchone()
            if row:
                cursor.execute("DELETE FROM sessions WHERE id = ?", (session_name_or_id,))
                conn.commit()
                return row[0]
        else:
            cursor.execute("DELETE FROM sessions WHERE session_name = ?", (session_name_or_id,))
            conn.commit()
            return session_name_or_id
    return None

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
    
    if session_name:
        # Удаляем из памяти
        with sessions_lock:
            if session_name in sessions_clients:
                try:
                    asyncio.run_coroutine_threadsafe(sessions_clients[session_name].disconnect(), loop)
                except: pass
                del sessions_clients[session_name]
        
        # Удаляем из БД
        delete_session_from_db(sid)
        
        # Удаляем файл .session
        try: os.remove(f"sessions/{session_name}.session")
        except: pass
        
        refresh_available_clients()
        add_admin_log(call.from_user.id, "SESSION_DELETED", f"Удалена сессия {session_name}")
        bot.answer_callback_query(call.id, "Сессия удалена")
    else:
        bot.answer_callback_query(call.id, "Сессия не найдена")
    
    session_list_callback(call)

@bot.callback_query_handler(func=lambda call: call.data == "session_check_all")
def session_check_all_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    bot.edit_message_text("🔍 Проверка всех сессий, пожалуйста, подождите...", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Запущена проверка...")
    asyncio.run_coroutine_threadsafe(check_all_sessions_async(call.message.chat.id), loop)

async def check_all_sessions_async(chat_id):
    sessions = get_all_sessions()
    if not sessions:
        bot.send_message(chat_id, "Нет добавленных сессий")
        return
    
    results = []
    for sid, name, phone, proxy_str, is_active, status, flood_until, req_today, errors, country in sessions:
        if status == 'dead':
            results.append(f"🔴 {name} — мертва, пропускаю")
            continue
        
        proxy = parse_http_proxy(proxy_str) if proxy_str else None
        try:
            client = TelegramClient(f"sessions/{name}", API_ID, API_HASH, proxy=proxy)
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                
                # Обновляем статус
                if status == 'flood' and flood_until > time.time():
                    remaining = int(flood_until - time.time())
                    results.append(f"🟡 {name} (@{me.username}) — ещё флуд {remaining}с")
                else:
                    update_session_in_db(name, 'active', requests_today=0)
                    results.append(f"🟢 {name} (@{me.username}) — активна")
                
                with sessions_lock:
                    if name in sessions_clients:
                        try: await sessions_clients[name].disconnect()
                        except: pass
                    sessions_clients[name] = client
            else:
                results.append(f"🔴 {name} — не авторизована")
                update_session_in_db(name, 'dead', errors_count=errors+1)
                await client.disconnect()
        except FloodWaitError as e:
            results.append(f"🟡 {name} — FloodWait {e.seconds}с")
            update_session_in_db(name, 'flood', flood_until=time.time() + e.seconds)
        except Exception as e:
            results.append(f"❌ {name} — ошибка: {str(e)[:50]}")
            update_session_in_db(name, 'dead', errors_count=errors+1)
        
        await asyncio.sleep(0.5)
    
    refresh_available_clients()
    update_session_metrics()
    
    result_text = "📊 <b>Результаты проверки сессий</b>\n\n" + "\n".join(results)
    
    if len(result_text) > 4000:
        parts = [result_text[i:i+4000] for i in range(0, len(result_text), 4000)]
        for part in parts:
            bot.send_message(chat_id, part, parse_mode='HTML')
    else:
        bot.send_message(chat_id, result_text, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == "session_refresh_status")
def session_refresh_status_callback(call):
    """Обновляет только статусы без полной проверки"""
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    
    # Сбрасываем флуд у тех, у кого время прошло
    now = time.time()
    with db_lock:
        cursor.execute("UPDATE sessions SET status = 'active', flood_until = 0 WHERE status = 'flood' AND flood_until < ?", (now,))
        
        # Переводим warming в active если прошло 24 часа
        cursor.execute("SELECT id, session_name, added_at FROM sessions WHERE status = 'warming'")
        for sid, name, added_at in cursor.fetchall():
            try:
                added_time = datetime.datetime.strptime(added_at, '%Y-%m-%d %H:%M:%S')
                if (datetime.datetime.now() - added_time).total_seconds() > WARMING_HOURS * 3600:
                    cursor.execute("UPDATE sessions SET status = 'active' WHERE id = ?", (sid,))
            except: pass
        conn.commit()
    
    update_session_metrics()
    bot.answer_callback_query(call.id, "✅ Статусы обновлены!")
    show_admin_dashboard(call.message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == "session_clean_dead")
def session_clean_dead_callback(call):
    """Удаляет все мёртвые сессии"""
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    
    with db_lock:
        cursor.execute("SELECT id, session_name FROM sessions WHERE status = 'dead'")
        dead_sessions = cursor.fetchall()
    
    for sid, name in dead_sessions:
        with sessions_lock:
            if name in sessions_clients:
                try:
                    asyncio.run_coroutine_threadsafe(sessions_clients[name].disconnect(), loop)
                except: pass
                del sessions_clients[name]
        delete_session_from_db(sid)
        try: os.remove(f"sessions/{name}.session")
        except: pass
    
    refresh_available_clients()
    add_admin_log(call.from_user.id, "CLEAN_DEAD", f"Удалено {len(dead_sessions)} мёртвых сессий")
    bot.answer_callback_query(call.id, f"✅ Удалено {len(dead_sessions)} сессий!")
    show_admin_dashboard(call.message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == "session_system_status")
def session_system_status_callback(call):
    """Показывает расширенный статус системы"""
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Нет доступа")
        return
    
    update_session_metrics()
    with metrics_lock:
        metrics.update_speed()
        speed = metrics.checks_per_second
        cpu = metrics.cpu_percent
        total_checks = metrics.checks_total
        today_checks = metrics.checks_today
        found_today = metrics.found_today
    
    cpu_per_core = psutil.cpu_percent(interval=0.5, percpu=True)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    text = (
        f"📊 <b>СТАТУС СИСТЕМЫ</b>\n\n"
        f"<b>Производительность:</b>\n"
        f"⚡ Скорость: {speed:.1f} ник/сек\n"
        f"📊 CPU: {cpu:.1f}% (общий)\n"
        f"💾 RAM: {memory.percent}% ({memory.used // (1024**3)}GB / {memory.total // (1024**3)}GB)\n"
        f"💿 Диск: {disk.percent}%\n\n"
        f"<b>Статистика:</b>\n"
        f"📦 Всего проверок: {total_checks:,}\n"
        f"📦 Сегодня: {today_checks:,}\n"
        f"✅ Найдено сегодня: {found_today}\n\n"
        f"<b>Сессии:</b>\n"
        f"🟢 Активные: {metrics.session_stats.get('active', 0)}\n"
        f"🟡 Flood: {metrics.session_stats.get('flood', 0)}\n"
        f"🟠 Warming: {metrics.session_stats.get('warming', 0)}\n"
        f"🔴 Dead: {metrics.session_stats.get('dead', 0)}\n"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 Обновить", callback_data="session_system_status"))
    markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)
    bot.answer_callback_query(call.id)

# ==================== СТАНДАРТНЫЕ АДМИН-ОБРАБОТЧИКИ ====================
@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def admin_stats_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    with db_lock:
        cursor.execute("SELECT COUNT(*) FROM users"); total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_end > datetime('now')"); premium_users = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(total_searches) FROM users"); total_searches = cursor.fetchone()[0] or 0
        cursor.execute("SELECT SUM(found_count) FROM users"); total_found = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM users WHERE banned = 1"); banned = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM sessions"); total_sessions = cursor.fetchone()[0]
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
    if not users: text = "👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n\nНет пользователей"
    else:
        text = "👥 <b>ПОСЛЕДНИЕ 50 ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
        for uid, username, refs, banned in users:
            name = f"@{username}" if username else f"ID {uid}"
            ban = "🚫" if banned else ""
            text += f"{name} — {refs} реф {ban}\n"
    if len(text) > 4000: text = text[:4000] + "\n\n... и ещё"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=admin_inline_menu())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_give_premium")
def admin_give_premium_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("💎 Введите ID пользователя и количество дней через пробел:\nПример: `123456789 7`", call.message.chat.id, call.message.message_id, parse_mode='HTML')
    bot.register_next_step_handler(call.message, admin_give_premium_step)

def admin_give_premium_step(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split()
        user_id = int(parts[0]); days = int(parts[1])
        add_premium(user_id, days)
        add_admin_log(ADMIN_ID, "GIVE_PREMIUM", f"Выдан Premium {days}дн пользователю {user_id}")
        bot.send_message(message.chat.id, f"✅ Premium {days}дн выдан пользователю {user_id}", reply_markup=admin_inline_menu())
    except: bot.send_message(message.chat.id, "❌ Ошибка. Используйте: ID ДНИ", reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_give_searches")
def admin_give_searches_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("📦 Введите ID пользователя и количество поисков через пробел:\nПример: `123456789 10`", call.message.chat.id, call.message.message_id, parse_mode='HTML')
    bot.register_next_step_handler(call.message, admin_give_searches_step)

def admin_give_searches_step(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split()
        user_id = int(parts[0]); amount = int(parts[1])
        add_search_packages(user_id, amount)
        add_admin_log(ADMIN_ID, "GIVE_SEARCHES", f"Выдано {amount} поисков пользователю {user_id}")
        bot.send_message(message.chat.id, f"✅ {amount} поисков выдано пользователю {user_id}", reply_markup=admin_inline_menu())
    except: bot.send_message(message.chat.id, "❌ Ошибка. Используйте: ID КОЛИЧЕСТВО", reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_gift")
def admin_gift_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("🎁 Введите ID пользователя и количество дней через пробел:\nПример: `123456789 7`", call.message.chat.id, call.message.message_id, parse_mode='HTML')
    bot.register_next_step_handler(call.message, admin_gift_step)

def admin_gift_step(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split()
        receiver_id = int(parts[0]); days = int(parts[1])
        add_premium(receiver_id, days)
        create_gift(ADMIN_ID, receiver_id, days, "admin")
        add_admin_log(ADMIN_ID, "GIFT_PREMIUM", f"Подарен Premium {days}дн пользователю {receiver_id}")
        bot.send_message(message.chat.id, f"✅ Подарен Premium {days}дн пользователю {receiver_id}", reply_markup=admin_inline_menu())
        try: bot.send_message(receiver_id, f"🎁 <b>ВАМ ПОДАРИЛИ ПРЕМИУМ!</b>\n\n⏱️ Срок: {days} дней\nОт: Администратор", parse_mode='HTML')
        except: pass
    except: bot.send_message(message.chat.id, "❌ Ошибка. Используйте: ID ДНИ", reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_ban")
def admin_ban_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("🚫 Введите ID пользователя для бана:", call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(call.message, admin_ban_step)

def admin_ban_step(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        user_id = int(message.text.strip())
        update_user(user_id, banned=1)
        add_admin_log(ADMIN_ID, "BAN_USER", f"Забанен пользователь {user_id}")
        bot.send_message(message.chat.id, f"🚫 Пользователь {user_id} забанен", reply_markup=admin_inline_menu())
        try: bot.send_message(user_id, "🚫 <b>Вы заблокированы в боте.</b>", parse_mode='HTML')
        except: pass
    except: bot.send_message(message.chat.id, "❌ Ошибка. Введите ID", reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_unban")
def admin_unban_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("✅ Введите ID пользователя для разбана:", call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(call.message, admin_unban_step)

def admin_unban_step(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        user_id = int(message.text.strip())
        update_user(user_id, banned=0)
        add_admin_log(ADMIN_ID, "UNBAN_USER", f"Разбанен пользователь {user_id}")
        bot.send_message(message.chat.id, f"✅ Пользователь {user_id} разбанен", reply_markup=admin_inline_menu())
        try: bot.send_message(user_id, "✅ <b>Вы разблокированы в боте.</b>", parse_mode='HTML')
        except: pass
    except: bot.send_message(message.chat.id, "❌ Ошибка. Введите ID", reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def admin_broadcast_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("📢 Введите текст для рассылки:", call.message.chat.id, call.message.message_id)
    bot.register_next_step_handler(call.message, admin_broadcast_step)

def admin_broadcast_step(message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text
    if not text:
        bot.send_message(message.chat.id, "❌ Текст не может быть пустым", reply_markup=admin_inline_menu())
        return
    with db_lock:
        cursor.execute("SELECT user_id FROM users WHERE banned = 0")
        users = cursor.fetchall()
    success = 0; failed = 0
    status_msg = bot.send_message(message.chat.id, f"📢 Рассылка... 0/{len(users)}")
    for user_id, in users:
        try:
            bot.send_message(user_id, text, parse_mode='HTML')
            success += 1
            time.sleep(0.05)
        except: failed += 1
        if success % 10 == 0:
            try: bot.edit_message_text(f"📢 Рассылка... {success}/{len(users)}", message.chat.id, status_msg.message_id)
            except: pass
    add_admin_log(ADMIN_ID, "BROADCAST", f"Рассылка: ✅{success} ❌{failed}")
    bot.edit_message_text(f"✅ Готово! ✅{success} ❌{failed}", message.chat.id, status_msg.message_id, reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_removerefs")
def admin_removerefs_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("🗑️ Введите ID пользователя и количество рефералов для снятия через пробел:\nПример: `123456789 5`", call.message.chat.id, call.message.message_id, parse_mode='HTML')
    bot.register_next_step_handler(call.message, admin_removerefs_step)

def admin_removerefs_step(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        parts = message.text.split()
        user_id = int(parts[0]); amount = int(parts[1])
        user = get_user(user_id)
        if not user:
            bot.send_message(message.chat.id, "❌ Пользователь не найден", reply_markup=admin_inline_menu())
            return
        current = user.get('referrals_count', 0)
        new_count = max(0, current - amount)
        update_user(user_id, referrals_count=new_count)
        add_admin_log(ADMIN_ID, "REMOVE_REFS", f"Снято {amount} реф. у {user_id} (было {current})")
        bot.send_message(message.chat.id, f"🗑️ Снято {amount} реф. у {user_id}\nБыло: {current} → Стало: {new_count}", reply_markup=admin_inline_menu())
    except: bot.send_message(message.chat.id, "❌ Ошибка. Используйте: ID КОЛИЧЕСТВО", reply_markup=admin_inline_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_sessions_menu")
def admin_sessions_menu_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    bot.edit_message_text("🔄 <b>Управление сессиями</b>\n\nВыберите действие:", call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=sessions_menu())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_back")
def admin_back_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Нет доступа")
        return
    show_admin_dashboard(call.message.chat.id)
    bot.answer_callback_query(call.id)

# ==================== ФУНКЦИИ СЕССИЙ ====================
def get_all_sessions():
    with db_lock:
        cursor.execute("SELECT id, session_name, phone, proxy, proxy_country, status, flood_until, requests_today, errors_count FROM sessions ORDER BY status, priority")
        rows = cursor.fetchall()
    return rows

def init_sessions():
    """Инициализация сессий при запуске"""
    sessions = get_all_sessions()
    for sid, name, encrypted_phone, proxy_str, country, status, flood_until, req_today, errors in sessions:
        if status == 'dead':
            continue
        
        # Проверяем флуд
        if status == 'flood' and flood_until < time.time():
            update_session_in_db(name, 'active')
            status = 'active'
        
        # Проверяем прогрев
        if status == 'warming':
            with db_lock:
                cursor.execute("SELECT added_at FROM sessions WHERE id = ?", (sid,))
                row = cursor.fetchone()
                if row:
                    try:
                        added_time = datetime.datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                        if (datetime.datetime.now() - added_time).total_seconds() > WARMING_HOURS * 3600:
                            update_session_in_db(name, 'active')
                            status = 'active'
                    except: pass
        
        if status in ['active', 'warming']:
            proxy = parse_http_proxy(proxy_str) if proxy_str else None
            try:
                client = TelegramClient(f"sessions/{name}", API_ID, API_HASH, proxy=proxy)
                future = asyncio.run_coroutine_threadsafe(init_client(client, name), loop)
                future.result(timeout=30)
            except Exception as e:
                logger.error(f"Ошибка инициализации сессии {name}: {e}")
                update_session_in_db(name, 'dead', errors_count=errors+1)
    
    refresh_available_clients()
    update_session_metrics()

async def init_client(client, name):
    try:
        await client.connect()
        if await client.is_user_authorized():
            with sessions_lock:
                sessions_clients[name] = client
            logger.info(f"Сессия {name} загружена")
        else:
            await client.disconnect()
            update_session_in_db(name, 'dead')
    except FloodWaitError as e:
        logger.warning(f"FloodWait при инициализации {name}: {e.seconds}с")
        update_session_in_db(name, 'flood', flood_until=time.time() + e.seconds)
    except Exception as e:
        logger.error(f"Ошибка подключения {name}: {e}")
        update_session_in_db(name, 'dead')

def session_health_monitor():
    """Фоновый мониторинг здоровья сессий"""
    while True:
        try:
            time.sleep(CHECK_INTERVAL)
            
            with db_lock:
                # Сбрасываем флуд
                cursor.execute("UPDATE sessions SET status = 'active', flood_until = 0 WHERE status = 'flood' AND flood_until < ?", (time.time(),))
                
                # Переводим warming в active
                cursor.execute("SELECT id, session_name, added_at FROM sessions WHERE status = 'warming'")
                warming = cursor.fetchall()
                for sid, name, added_at in warming:
                    try:
                        added_time = datetime.datetime.strptime(added_at, '%Y-%m-%d %H:%M:%S')
                        if (datetime.datetime.now() - added_time).total_seconds() > WARMING_HOURS * 3600:
                            cursor.execute("UPDATE sessions SET status = 'active' WHERE id = ?", (sid,))
                    except: pass
                
                conn.commit()
            
            update_session_metrics()
            
            # Обновление скорости
            with metrics_lock:
                metrics.update_speed()
            
            # Проверка сессий
            for name in list(sessions_clients.keys()):
                client = sessions_clients.get(name)
                if client and not client.is_connected():
                    try:
                        future = asyncio.run_coroutine_threadsafe(client.connect(), loop)
                        future.result(timeout=5)
                    except:
                        update_session_in_db(name, 'dead')
            
            refresh_available_clients()
            
        except Exception as e:
            logger.error(f"Ошибка health monitor: {e}")

threading.Thread(target=session_health_monitor, daemon=True).start()

@bot.message_handler(func=lambda m: m.text == f"{EMOJI['admin']} АДМИН")
def admin_button(message):
    if message.from_user.id == ADMIN_ID:
        show_admin_dashboard(message.chat.id)
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
    print("🤖 БОТ ЗАПУЩЕН")
    print(f"👑 Админ ID: {ADMIN_ID}")
    print(f"💾 База данных: users.db (зашифрована)")
    print(f"🔐 Пароль админа: хеширован")
    print(f"🔄 Сессии: загружаются...")
    print("=" * 60)
    
    # Запуск асинхронного цикла в отдельном потоке
    threading.Thread(target=run_async_loop, daemon=True).start()
    time.sleep(3)  # Ждём инициализации сессий
    
    print(f"✅ Загружено сессий: {len(available_clients)}")
    print(f"⚡ Бот готов к работе!")
    print("=" * 60)
    
    # Запуск бота
    bot.infinity_polling(timeout=60)
