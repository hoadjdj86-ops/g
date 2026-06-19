#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import json
import logging
import random
import uuid
import threading
import aiohttp
import re
import asyncio
import io
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from PIL import Image, ImageDraw, ImageFont
import os

# ============================================================
# CONFIGURATION
# ============================================================

DISCORD_TOKEN = "MTUxNjk1NjQ5ODY2MjUyNzEwNw.GqA04D.lAZLQ-mq3BTppK9iBQPbUjClakUcifMRd147TI"
DATABASE_PATH = "rocky_store.db"
COMMAND_PREFIX = "!"
GIFT_COOLDOWN_HOURS = 24
LOG_LEVEL = "INFO"
LOGO_URL = "https://media.discordapp.net/attachments/1502908967456604173/1517035301585813525/IMG_0540.png?ex=6a34d0b9&is=6a337f39&hm=d3512bff4ffd0f8fbe314e063e5a43760428a6392e63dacc88f9c0946024abdb&=&format=webp&quality=lossless&width=760&height=760"

GUILD_ID = 1502908967448481842

logging.basicConfig(level=getattr(logging, LOG_LEVEL), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('RockyStore_BOT')

# ============================================================
# IMAGE PROCESSING FUNCTION
# ============================================================

async def add_logo_to_image(image_url: str, logo_url: str = LOGO_URL) -> Optional[bytes]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status != 200:
                    return None
                img_data = await resp.read()
            
            async with session.get(logo_url) as resp:
                if resp.status != 200:
                    return None
                logo_data = await resp.read()
        
        img = Image.open(io.BytesIO(img_data)).convert("RGBA")
        logo = Image.open(io.BytesIO(logo_data)).convert("RGBA")
        
        logo_width = int(img.width * 0.4)
        logo_height = int(logo.height * (logo_width / logo.width))
        logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
        
        logo_alpha = logo.split()[3]
        logo_alpha = logo_alpha.point(lambda p: p * 0.3)
        logo.putalpha(logo_alpha)
        
        x = (img.width - logo.width) // 2
        y = (img.height - logo.height) // 2
        
        img.paste(logo, (x, y), logo)
        
        output = io.BytesIO()
        img.save(output, format="PNG")
        output.seek(0)
        return output.read()
        
    except Exception as e:
        logger.error(f"Error adding logo: {e}")
        return None

# ============================================================
# DATABASE
# ============================================================

class Database:
    _instance = None
    _lock = threading.Lock()
    def __new__(cls, db_path: str = DATABASE_PATH):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Database, cls).__new__(cls)
                cls._instance._initialize(db_path)
        return cls._instance
    def _initialize(self, db_path: str):
        self.db_path = db_path
        self._create_tables()
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    def _create_tables(self):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, username TEXT NOT NULL, discriminator TEXT, avatar_url TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP, exploration_hours INTEGER DEFAULT 0, total_references_generated INTEGER DEFAULT 0, gifts_opened INTEGER DEFAULT 0, gift_cooldown_until TIMESTAMP, metadata TEXT DEFAULT "{}")')
            c.execute('CREATE TABLE IF NOT EXISTS refs (reference_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, product TEXT NOT NULL, text_content TEXT NOT NULL, image_url TEXT, generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, is_active INTEGER DEFAULT 1, metadata TEXT DEFAULT "{}", FOREIGN KEY (user_id) REFERENCES users(user_id))')
            c.execute('CREATE TABLE IF NOT EXISTS gifts (gift_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, gift_type TEXT NOT NULL, content TEXT, opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, is_claimed INTEGER DEFAULT 0, metadata TEXT DEFAULT "{}", FOREIGN KEY (user_id) REFERENCES users(user_id))')
            c.execute('CREATE TABLE IF NOT EXISTS waves (wave_id TEXT PRIMARY KEY, from_user_id TEXT NOT NULL, to_user_id TEXT NOT NULL, waved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, metadata TEXT DEFAULT "{}", FOREIGN KEY (from_user_id) REFERENCES users(user_id), FOREIGN KEY (to_user_id) REFERENCES users(user_id))')
            c.execute('CREATE TABLE IF NOT EXISTS payment_triggers (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT NOT NULL, prefix TEXT NOT NULL, message TEXT NOT NULL, created_by TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, is_active INTEGER DEFAULT 1, metadata TEXT DEFAULT "{}", UNIQUE(guild_id, prefix))')
            c.execute('CREATE TABLE IF NOT EXISTS auto_reply_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT NOT NULL, channel_id TEXT NOT NULL, message TEXT NOT NULL, include_original INTEGER DEFAULT 0, created_by TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, is_active INTEGER DEFAULT 1, metadata TEXT DEFAULT "{}", UNIQUE(guild_id, channel_id))')
            c.execute('CREATE TABLE IF NOT EXISTS embed_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id TEXT NOT NULL, channel_id TEXT NOT NULL, message TEXT NOT NULL, image_url TEXT, sent_by TEXT NOT NULL, sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, metadata TEXT DEFAULT "{}")')
            c.execute('CREATE TABLE IF NOT EXISTS social_links (user_id TEXT PRIMARY KEY, instagram TEXT, tiktok TEXT, twitter TEXT, youtube TEXT, FOREIGN KEY (user_id) REFERENCES users(user_id))')
            c.execute('CREATE TABLE IF NOT EXISTS autorole_config (guild_id TEXT PRIMARY KEY, role_id TEXT NOT NULL, enabled INTEGER DEFAULT 1)')
            c.execute('CREATE TABLE IF NOT EXISTS tickets (ticket_id TEXT PRIMARY KEY, guild_id TEXT NOT NULL, channel_id TEXT NOT NULL, creator_id TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT "open", metadata TEXT DEFAULT "{}")')
            c.execute('CREATE TABLE IF NOT EXISTS ticket_configs (guild_id TEXT PRIMARY KEY, mensaje TEXT, emoji TEXT, canal_id TEXT, categoria_id TEXT, descripcion_id TEXT, imagen1 TEXT, imagen2 TEXT, imagen3 TEXT, imagen4 TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS mutes (user_id TEXT NOT NULL, guild_id TEXT NOT NULL, until TIMESTAMP, reason TEXT, PRIMARY KEY (user_id, guild_id))')
            c.execute('CREATE TABLE IF NOT EXISTS wordle_scores (user_id TEXT PRIMARY KEY, games_played INTEGER DEFAULT 0, games_won INTEGER DEFAULT 0, current_streak INTEGER DEFAULT 0, max_streak INTEGER DEFAULT 0, total_guesses INTEGER DEFAULT 0, FOREIGN KEY (user_id) REFERENCES users(user_id))')
            c.execute('CREATE TABLE IF NOT EXISTS wordle_games (user_id TEXT PRIMARY KEY, answer TEXT NOT NULL, guesses TEXT DEFAULT "[]", attempts INTEGER DEFAULT 0, max_attempts INTEGER DEFAULT 6, status TEXT DEFAULT "playing", FOREIGN KEY (user_id) REFERENCES users(user_id))')
            conn.commit()

    def get_or_create_user(self, user_id: str, username: str, discriminator: str = "0", avatar_url: str = "") -> Dict[str, Any]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            if row:
                c.execute('UPDATE users SET username = ?, discriminator = ?, avatar_url = ?, last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (username, discriminator, avatar_url, user_id))
                conn.commit()
                return dict(row)
            else:
                c.execute('INSERT INTO users (user_id, username, discriminator, avatar_url, gift_cooldown_until) VALUES (?, ?, ?, ?, ?)', (user_id, username, discriminator, avatar_url, datetime.utcnow().isoformat()))
                conn.commit()
                c.execute('INSERT OR IGNORE INTO wordle_scores (user_id) VALUES (?)', (user_id,))
                conn.commit()
                c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
                return dict(c.fetchone())

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def update_user_exploration(self, user_id: str, hours: int) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET exploration_hours = exploration_hours + ?, last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (hours, user_id))
            conn.commit()
            return c.rowcount > 0

    def can_open_gift(self, user_id: str) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT gift_cooldown_until FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            if not row or not row['gift_cooldown_until']:
                return True
            return datetime.utcnow() >= datetime.fromisoformat(row['gift_cooldown_until'])

    def set_gift_cooldown(self, user_id: str, hours: int = 24) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            cooldown_time = (datetime.utcnow() + timedelta(hours=hours)).isoformat()
            c.execute('UPDATE users SET gift_cooldown_until = ?, gifts_opened = gifts_opened + 1, last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (cooldown_time, user_id))
            conn.commit()
            return c.rowcount > 0

    def generate_reference(self, user_id: str, product: str, text_content: str, image_url: str = None, metadata: Dict = None) -> str:
        ref_id = str(uuid.uuid4())[:8].upper()
        metadata_json = json.dumps(metadata or {})
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT INTO refs (reference_id, user_id, product, text_content, image_url, metadata) VALUES (?, ?, ?, ?, ?, ?)',
                      (ref_id, user_id, product, text_content, image_url, metadata_json))
            c.execute('UPDATE users SET total_references_generated = total_references_generated + 1, last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (user_id,))
            conn.commit()
            return ref_id

    def get_reference(self, reference_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT r.*, u.username, u.discriminator FROM refs r JOIN users u ON r.user_id = u.user_id WHERE r.reference_id = ? AND r.is_active = 1', (reference_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def get_user_references(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM refs WHERE user_id = ? AND is_active = 1 ORDER BY generated_at DESC LIMIT ?', (user_id, limit))
            return [dict(row) for row in c.fetchall()]

    def deactivate_reference(self, reference_id: str, user_id: str) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE refs SET is_active = 0 WHERE reference_id = ? AND user_id = ?', (reference_id, user_id))
            conn.commit()
            return c.rowcount > 0

    def add_gift(self, user_id: str, gift_type: str, content: str, metadata: Dict = None) -> str:
        gift_id = str(uuid.uuid4())[:8].upper()
        metadata_json = json.dumps(metadata or {})
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT INTO gifts (gift_id, user_id, gift_type, content, metadata) VALUES (?, ?, ?, ?, ?)', (gift_id, user_id, gift_type, content, metadata_json))
            conn.commit()
            return gift_id

    def get_unclaimed_gifts(self, user_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM gifts WHERE user_id = ? AND is_claimed = 0 ORDER BY opened_at ASC', (user_id,))
            return [dict(row) for row in c.fetchall()]

    def claim_gift(self, gift_id: str, user_id: str) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE gifts SET is_claimed = 1 WHERE gift_id = ? AND user_id = ? AND is_claimed = 0', (gift_id, user_id))
            conn.commit()
            return c.rowcount > 0

    def record_wave(self, from_user_id: str, to_user_id: str, metadata: Dict = None) -> str:
        wave_id = str(uuid.uuid4())[:8].upper()
        metadata_json = json.dumps(metadata or {})
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT INTO waves (wave_id, from_user_id, to_user_id, metadata) VALUES (?, ?, ?, ?)', (wave_id, from_user_id, to_user_id, metadata_json))
            conn.commit()
            return wave_id

    def get_wave_count(self, user_id: str) -> int:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) as count FROM waves WHERE to_user_id = ?', (user_id,))
            row = c.fetchone()
            return row['count'] if row else 0

    def get_waves_to_user(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT w.*, u.username as from_username, u.discriminator as from_discriminator FROM waves w JOIN users u ON w.from_user_id = u.user_id WHERE w.to_user_id = ? ORDER BY w.waved_at DESC LIMIT ?', (user_id, limit))
            return [dict(row) for row in c.fetchall()]

    def create_payment_trigger(self, guild_id: str, prefix: str, message: str, created_by: str) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            try:
                c.execute('INSERT OR REPLACE INTO payment_triggers (guild_id, prefix, message, created_by, is_active) VALUES (?, ?, ?, ?, 1)', (guild_id, prefix.lower(), message, created_by))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def list_payment_triggers(self, guild_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM payment_triggers WHERE guild_id = ? AND is_active = 1 ORDER BY created_at DESC', (guild_id,))
            return [dict(row) for row in c.fetchall()]

    def delete_payment_trigger(self, guild_id: str, prefix: str) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE payment_triggers SET is_active = 0 WHERE guild_id = ? AND prefix = ?', (guild_id, prefix.lower()))
            conn.commit()
            return c.rowcount > 0

    def create_auto_reply(self, guild_id: str, channel_id: str, message: str, created_by: str, include_original: bool = False) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            try:
                c.execute('INSERT OR REPLACE INTO auto_reply_configs (guild_id, channel_id, message, include_original, created_by, is_active) VALUES (?, ?, ?, ?, ?, 1)', (guild_id, channel_id, message, 1 if include_original else 0, created_by))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_auto_reply(self, guild_id: str, channel_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM auto_reply_configs WHERE guild_id = ? AND channel_id = ? AND is_active = 1', (guild_id, channel_id))
            row = c.fetchone()
            return dict(row) if row else None

    def list_auto_replies(self, guild_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM auto_reply_configs WHERE guild_id = ? AND is_active = 1 ORDER BY created_at DESC', (guild_id,))
            return [dict(row) for row in c.fetchall()]

    def delete_auto_reply(self, guild_id: str, channel_id: str) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE auto_reply_configs SET is_active = 0 WHERE guild_id = ? AND channel_id = ?', (guild_id, channel_id))
            conn.commit()
            return c.rowcount > 0

    def log_embed_send(self, guild_id: str, channel_id: str, message: str, image_url: Optional[str], sent_by: str) -> int:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT INTO embed_logs (guild_id, channel_id, message, image_url, sent_by) VALUES (?, ?, ?, ?, ?)', (guild_id, channel_id, message, image_url, sent_by))
            conn.commit()
            return c.lastrowid

    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT user_id, username, total_references_generated, exploration_hours, gifts_opened, (total_references_generated * 10 + exploration_hours * 2 + gifts_opened * 5) as score FROM users ORDER BY score DESC LIMIT ?', (limit,))
            return [dict(row) for row in c.fetchall()]

    def set_social_link(self, user_id: str, platform: str, url: str) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute(f'INSERT OR REPLACE INTO social_links (user_id, {platform}) VALUES (?, ?)', (user_id, url))
            conn.commit()
            return c.rowcount > 0

    def get_social_links(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM social_links WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def set_autorole(self, guild_id: str, role_id: str) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO autorole_config (guild_id, role_id, enabled) VALUES (?, ?, 1)', (guild_id, role_id))
            conn.commit()
            return c.rowcount > 0

    def get_autorole(self, guild_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM autorole_config WHERE guild_id = ? AND enabled = 1', (guild_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def disable_autorole(self, guild_id: str) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE autorole_config SET enabled = 0 WHERE guild_id = ?', (guild_id,))
            conn.commit()
            return c.rowcount > 0

    def create_ticket(self, ticket_id: str, guild_id: str, channel_id: str, creator_id: str) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT INTO tickets (ticket_id, guild_id, channel_id, creator_id) VALUES (?, ?, ?, ?)', (ticket_id, guild_id, channel_id, creator_id))
            conn.commit()
            return c.rowcount > 0

    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM tickets WHERE ticket_id = ? AND status = "open"', (ticket_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def close_ticket(self, ticket_id: str) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE tickets SET status = "closed" WHERE ticket_id = ?', (ticket_id,))
            conn.commit()
            return c.rowcount > 0

    def get_tickets_by_channel(self, channel_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM tickets WHERE channel_id = ? AND status = "open"', (channel_id,))
            return [dict(row) for row in c.fetchall()]

    def get_tickets_by_creator(self, user_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM tickets WHERE creator_id = ? AND status = "open"', (user_id,))
            return [dict(row) for row in c.fetchall()]

    def set_ticket_config(self, guild_id: str, mensaje: str, emoji: str, canal_id: str, categoria_id: str, descripcion_id: str, imagen1: str = None, imagen2: str = None, imagen3: str = None, imagen4: str = None) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO ticket_configs (guild_id, mensaje, emoji, canal_id, categoria_id, descripcion_id, imagen1, imagen2, imagen3, imagen4) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      (guild_id, mensaje, emoji, canal_id, categoria_id, descripcion_id, imagen1, imagen2, imagen3, imagen4))
            conn.commit()
            return c.rowcount > 0

    def get_ticket_config(self, guild_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM ticket_configs WHERE guild_id = ?', (guild_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def add_mute(self, user_id: str, guild_id: str, until: datetime, reason: str = "") -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO mutes (user_id, guild_id, until, reason) VALUES (?, ?, ?, ?)', (user_id, guild_id, until.isoformat(), reason))
            conn.commit()
            return c.rowcount > 0

    def remove_mute(self, user_id: str, guild_id: str) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM mutes WHERE user_id = ? AND guild_id = ?', (user_id, guild_id))
            conn.commit()
            return c.rowcount > 0

    def get_mute(self, user_id: str, guild_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM mutes WHERE user_id = ? AND guild_id = ?', (user_id, guild_id))
            row = c.fetchone()
            return dict(row) if row else None

    def get_expired_mutes(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            now = datetime.utcnow().isoformat()
            c.execute('SELECT * FROM mutes WHERE until <= ?', (now,))
            return [dict(row) for row in c.fetchall()]

    def get_wordle_score(self, user_id: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM wordle_scores WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            if not row:
                c.execute('INSERT INTO wordle_scores (user_id) VALUES (?)', (user_id,))
                conn.commit()
                c.execute('SELECT * FROM wordle_scores WHERE user_id = ?', (user_id,))
                row = c.fetchone()
            return dict(row)

    def update_wordle_score(self, user_id: str, won: bool, guesses: int):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM wordle_scores WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            if not row:
                c.execute('INSERT INTO wordle_scores (user_id) VALUES (?)', (user_id,))
                conn.commit()
                c.execute('SELECT * FROM wordle_scores WHERE user_id = ?', (user_id,))
                row = c.fetchone()
            games_played = row['games_played'] + 1
            games_won = row['games_won'] + (1 if won else 0)
            current_streak = row['current_streak'] + 1 if won else 0
            max_streak = max(row['max_streak'], current_streak)
            total_guesses = row['total_guesses'] + guesses
            c.execute('UPDATE wordle_scores SET games_played = ?, games_won = ?, current_streak = ?, max_streak = ?, total_guesses = ? WHERE user_id = ?',
                      (games_played, games_won, current_streak, max_streak, total_guesses, user_id))
            conn.commit()

    def get_wordle_game(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM wordle_games WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def create_wordle_game(self, user_id: str, answer: str):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO wordle_games (user_id, answer, guesses, attempts, status) VALUES (?, ?, ?, ?, ?)',
                      (user_id, answer, json.dumps([]), 0, "playing"))
            conn.commit()

    def update_wordle_game(self, user_id: str, guesses: List[str], attempts: int, status: str):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE wordle_games SET guesses = ?, attempts = ?, status = ? WHERE user_id = ?',
                      (json.dumps(guesses), attempts, status, user_id))
            conn.commit()

    def delete_wordle_game(self, user_id: str):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM wordle_games WHERE user_id = ?', (user_id,))
            conn.commit()

# ============================================================
# TICKET BUTTONS
# ============================================================

class TranscribeButton(discord.ui.View):
    def __init__(self, ticket_id: str, creator_id: str):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.creator_id = creator_id
    
    @discord.ui.button(label="📝 Transcribir Ticket", style=discord.ButtonStyle.secondary, custom_id="transcribe_ticket")
    async def transcribe_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith('ticket-'):
            await interaction.response.send_message("❌ Este no es un canal de tickets.", ephemeral=True)
            return
        
        if str(interaction.user.id) != self.creator_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Solo el creador del ticket o un administrador puede transcribirlo.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            messages = []
            async for msg in interaction.channel.history(limit=200, oldest_first=True):
                timestamp = msg.created_at.strftime("%d/%m/%Y %H:%M")
                content = msg.content if msg.content else ""
                attachments = " ".join([a.url for a in msg.attachments]) if msg.attachments else ""
                messages.append(f"[{timestamp}] {msg.author.display_name}: {content} {attachments}".strip())
            
            if not messages:
                await interaction.followup.send("❌ No hay mensajes para transcribir.", ephemeral=True)
                return
            
            transcript = "\n".join(messages)
            transcript_bytes = transcript.encode('utf-8')
            file = discord.File(io.BytesIO(transcript_bytes), filename=f"transcript_{self.ticket_id}.txt")
            
            await interaction.followup.send(f"📝 Transcripción del ticket `{self.ticket_id}`:", file=file, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Error al transcribir: {str(e)}", ephemeral=True)

class CloseTicketButton(discord.ui.View):
    def __init__(self, ticket_id: str):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
    
    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith('ticket-'):
            await interaction.response.send_message("❌ Este no es un canal de tickets.", ephemeral=True)
            return
        
        ticket_data = db.get_tickets_by_channel(str(interaction.channel.id))
        if not ticket_data:
            await interaction.response.send_message("❌ No se encontró el ticket.", ephemeral=True)
            return
        
        ticket = ticket_data[0]
        creator_id = ticket['creator_id']
        
        if str(interaction.user.id) != creator_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Solo el creador del ticket o un administrador puede cerrarlo.", ephemeral=True)
            return
        
        db.close_ticket(self.ticket_id)
        
        await interaction.response.send_message("🔒 Cerrando ticket en 5 segundos...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class OpenTicketButton(discord.ui.View):
    def __init__(self, guild_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
    
    @discord.ui.button(label="🎫 Abrir Ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Error: No se encontró el servidor.", ephemeral=True)
            return
        
        config = db.get_ticket_config(str(guild.id))
        if not config:
            await interaction.response.send_message("❌ El sistema de tickets no está configurado.", ephemeral=True)
            return
        
        member = interaction.user
        
        existing_tickets = db.get_tickets_by_creator(str(member.id))
        if existing_tickets:
            for t in existing_tickets:
                channel = guild.get_channel(int(t['channel_id']))
                if channel:
                    await interaction.response.send_message(f"❌ Ya tienes un ticket abierto en {channel.mention}", ephemeral=True)
                    return
        
        category = None
        if config.get('categoria_id'):
            category = guild.get_channel(int(config['categoria_id']))
        if not category:
            category = discord.utils.get(guild.categories, name="Tickets")
            if not category:
                category = await guild.create_category("Tickets")
        
        ticket_id = str(uuid.uuid4())[:8].upper()
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        
        admin_role = discord.utils.get(guild.roles, name="Admin")
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        
        staff_role = discord.utils.get(guild.roles, name="Staff")
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        
        ticket_channel = await category.create_text_channel(
            f"ticket-{member.name}",
            overwrites=overwrites
        )
        
        db.create_ticket(ticket_id, str(guild.id), str(ticket_channel.id), str(member.id))
        
        if config.get('descripcion_id'):
            desc_channel = guild.get_channel(int(config['descripcion_id']))
            if desc_channel:
                desc_embed = discord.Embed(
                    title="🎫 Nuevo Ticket",
                    description=f"**Usuario:** {member.mention}\n**Ticket:** {ticket_channel.mention}\n**ID:** `{ticket_id}`",
                    color=0x00FF00
                )
                await desc_channel.send("@everyone", embed=desc_embed)
        
        view = discord.ui.View()
        view.add_item(CloseTicketButton(ticket_id).children[0])
        view.add_item(TranscribeButton(ticket_id, str(member.id)).children[0])
        
        embed = discord.Embed(
            title="🎫 ¡Ticket Abierto!",
            description=f"Bienvenido {member.mention}!\n\nUn miembro del equipo te atenderá pronto.\n\nUsa los botones de abajo para cerrar o transcribir el ticket.",
            color=0x00BFFF
        )
        embed.add_field(name="📌 ID del Ticket", value=f"`{ticket_id}`", inline=False)
        await ticket_channel.send(member.mention, embed=embed, view=view)
        
        await interaction.response.send_message(f"✅ Ticket abierto en {ticket_channel.mention}", ephemeral=True)

# ============================================================
# BOT
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True

class RockyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)
        self.synced = False
        self.start_time = datetime.utcnow()
        self.db = Database()
        self.vc_data = {}
        self.guild = None
    async def setup_hook(self):
        try:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"✅ Slash commands synced instantly to guild ID: {GUILD_ID}")
        except Exception as e:
            logger.error(f"Failed to sync to guild: {e}")
            await self.tree.sync()
            logger.info("⚠️ Commands synced globally (may take up to 1 hour)")
        self.synced = True
    async def on_ready(self):
        logger.info(f"✅ Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"✅ Connected to {len(self.guilds)} guilds")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{len(self.guilds)} servers | /help"))

bot = RockyBot()
db = bot.db

@bot.event
async def on_member_join(member: discord.Member):
    try:
        db.get_or_create_user(str(member.id), member.name, member.discriminator, member.display_avatar.url if member.avatar else "")
        autorole = db.get_autorole(str(member.guild.id))
        if autorole:
            role = member.guild.get_role(int(autorole['role_id']))
            if role:
                try:
                    await member.add_roles(role, reason="Autorole")
                except:
                    pass
    except Exception as e:
        logger.error(f"Error on member join {member.id}: {e}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    try:
        db.get_or_create_user(str(interaction.user.id), interaction.user.name, interaction.user.discriminator, interaction.user.display_avatar.url)
    except Exception as e:
        logger.error(f"Error logging interaction user {interaction.user.id}: {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return
    
    guild_id = str(message.guild.id)
    channel_id = str(message.channel.id)
    content = message.content.strip()
    
    for trigger in db.list_payment_triggers(guild_id):
        if content.startswith(trigger['prefix']):
            rest = content[len(trigger['prefix']):].strip()
            embed = discord.Embed(title="💳 Payment Order", description=trigger['message'], color=0x00FF00)
            if rest:
                embed.add_field(name="📝 Additional Info", value=rest, inline=False)
            embed.add_field(name="👤 Requested By", value=message.author.mention, inline=True)
            await message.channel.send(embed=embed)
            break
    
    # AUTO-REPLY - SIN TÍTULO "🔁 Auto-Reply"
    auto_reply = db.get_auto_reply(guild_id, channel_id)
    if auto_reply and not content.startswith('/') and not content.startswith('!'):
        reply = auto_reply['message']
        if auto_reply['include_original']:
            reply = f"**{message.author.display_name} said:**\n{content}\n\n{reply}"
        # Enviar como mensaje plano SIN embed
        await message.channel.send(reply)
    
    if message.channel.name.startswith('ticket-'):
        ticket_data = db.get_tickets_by_channel(str(message.channel.id))
        if ticket_data:
            ticket = ticket_data[0]
            creator_id = ticket['creator_id']
            if str(message.author.id) != creator_id:
                try:
                    user = await bot.fetch_user(int(creator_id))
                    if user:
                        dm_embed = discord.Embed(
                            title=f"📩 Nuevo mensaje en tu ticket",
                            description=f"**Canal:** {message.channel.mention}\n**Autor:** {message.author.mention}\n\n**Mensaje:**\n{content}",
                            color=0x00BFFF
                        )
                        if message.attachments:
                            dm_embed.add_field(name="📎 Adjuntos", value=f"{len(message.attachments)} archivo(s)", inline=False)
                        await user.send(embed=dm_embed)
                except:
                    pass
    
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.id == bot.user.id and after.channel is None:
        guild_id = str(member.guild.id)
        if guild_id in bot.vc_data:
            del bot.vc_data[guild_id]

# ============================================================
# PREFIX COMMANDS
# ============================================================

@bot.command(name='help')
async def help_prefix(ctx):
    embed = discord.Embed(
        title="📋 Rocky Store • Comandos",
        description="**📋 Comandos principales**\n/refe – Generar referencia con imagen\n/config – Enviar embed con hasta 4 imágenes\n/regalo – Abrir regalo (24h cooldown)\n/onda – Enviar onda\n/tabla – Tabla de clasificación\n/perfil – Ver perfil\n\n"
        "**🎟️ Tickets**\n/crear_tickets – Configurar sistema de tickets\n/configurar_tickets – Alias de crear_tickets\n\n"
        "**😀 Emojis**\n/add_emoji – Robar emoji de otro servidor\n\n"
        "**🎮 Juegos**\n/wordle – Jugar Wordle\n/wordle_guess – Adivinar\n/wordle_stats – Estadísticas\n\n"
        "**🛡️ Moderación**\n/banear /expulsar /silenciar /desilenciar /limpiar /bloquear /desbloquear\n\n"
        "**📨 Admin**\n/crear_trigger /configurar_auto /listar_configs /eliminar_config /rol_auto /color /avatar /id_usuario /autor /instagram /tiktok /unirse /salir /antiraid",
        color=0x00BFFF
    )
    await ctx.send(embed=embed)

@bot.command(name='cerrar_ticket')
async def cerrar_ticket(ctx):
    try:
        if not ctx.channel.name.startswith('ticket-'):
            embed = discord.Embed(title="❌ Error", description="Este no es un canal de tickets.", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        
        ticket_data = db.get_tickets_by_channel(str(ctx.channel.id))
        if not ticket_data:
            embed = discord.Embed(title="❌ Error", description="No se encontró el ticket.", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        
        ticket = ticket_data[0]
        creator_id = ticket['creator_id']
        
        if str(ctx.author.id) != creator_id and not ctx.author.guild_permissions.administrator:
            embed = discord.Embed(title="❌ Error", description="Solo el creador del ticket o un administrador puede cerrarlo.", color=0xFF0000)
            await ctx.send(embed=embed)
            return
        
        db.close_ticket(ticket['ticket_id'])
        
        await ctx.send("🔒 Cerrando ticket en 5 segundos...")
        await asyncio.sleep(5)
        await ctx.channel.delete()
        
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await ctx.send(embed=embed)

# ============================================================
# SLASH COMMANDS
# ============================================================

# ---------- HELP ----------
@bot.tree.command(name="help", description="Muestra todos los comandos disponibles")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📋 Rocky Store • Comandos",
        description="**📋 Comandos principales**\n/refe – Generar referencia con imagen\n/config – Enviar embed con hasta 4 imágenes\n/regalo – Abrir regalo (24h cooldown)\n/onda – Enviar onda\n/tabla – Tabla de clasificación\n/perfil – Ver perfil\n\n"
        "**🎟️ Tickets**\n/crear_tickets – Configurar sistema de tickets\n/configurar_tickets – Alias de crear_tickets\n\n"
        "**😀 Emojis**\n/add_emoji – Robar emoji de otro servidor\n\n"
        "**🎮 Juegos**\n/wordle /wordle_guess /wordle_stats\n\n"
        "**🛡️ Moderación**\n/banear /expulsar /silenciar /desilenciar /limpiar /bloquear /desbloquear\n\n"
        "**📨 Admin**\n/crear_trigger /configurar_auto /listar_configs /eliminar_config /rol_auto /color /avatar /id_usuario /autor /instagram /tiktok /unirse /salir /antiraid",
        color=0x00BFFF
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------- REFE ----------
@bot.tree.command(name="refe", description="Genera una referencia (solo @Clientes)")
@app_commands.describe(
    producto="Nombre del producto",
    reseña="Reseña del producto",
    imagen="Adjunta una imagen (OBLIGATORIO)"
)
@app_commands.default_permissions()
async def slash_refe(
    interaction: discord.Interaction,
    producto: str,
    reseña: str,
    imagen: discord.Attachment
):
    clientes_role = discord.utils.get(interaction.guild.roles, name="Clientes")
    if not clientes_role:
        embed = discord.Embed(title="❌ Error", description="El rol `@Clientes` no existe en este servidor.", color=0xFF0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if clientes_role not in interaction.user.roles:
        embed = discord.Embed(title="❌ Permiso Denegado", description="Necesitas el rol `@Clientes` para usar este comando.", color=0xFF0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.defer()

    user_id = str(interaction.user.id)
    image_url = imagen.url

    logo_image_bytes = await add_logo_to_image(image_url)
    
    if logo_image_bytes:
        try:
            file = discord.File(io.BytesIO(logo_image_bytes), filename="reference_with_logo.png")
            ref_id = db.generate_reference(user_id, producto, reseña, image_url)
            
            embed = discord.Embed(
                title="📋 Referencia Generada",
                description=f"**Producto:** {producto}\n**Reseña:** {reseña}",
                color=0x00BFFF
            )
            embed.add_field(name="🔑 ID", value=f"`{ref_id}`", inline=False)
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.set_image(url="attachment://reference_with_logo.png")
            
            await interaction.followup.send(file=file, embed=embed)
            return
        except Exception as e:
            logger.error(f"Error uploading logo image: {e}")
    
    ref_id = db.generate_reference(user_id, producto, reseña, image_url)
    embed = discord.Embed(
        title="📋 Referencia Generada",
        description=f"**Producto:** {producto}\n**Reseña:** {reseña}",
        color=0x00BFFF
    )
    embed.add_field(name="🔑 ID", value=f"`{ref_id}`", inline=False)
    embed.set_image(url=image_url)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    await interaction.followup.send(embed=embed)

# ---------- CONFIG ----------
@bot.tree.command(name="config", description="Enviar un embed con mensaje y hasta 4 imágenes")
@app_commands.describe(
    canal="Canal donde enviar el embed",
    mensaje="Mensaje del embed",
    titulo="Título del embed (opcional)",
    imagen1="URL de imagen 1 (opcional)",
    imagen2="URL de imagen 2 (opcional)",
    imagen3="URL de imagen 3 (opcional)",
    imagen4="URL de imagen 4 (opcional)",
    color="Color del embed en hex (ej: #FF0000) - opcional"
)
@commands.has_permissions(administrator=True)
async def slash_config(
    interaction: discord.Interaction,
    canal: discord.TextChannel,
    mensaje: str,
    titulo: str = None,
    imagen1: str = None,
    imagen2: str = None,
    imagen3: str = None,
    imagen4: str = None,
    color: str = None
):
    await interaction.response.defer(ephemeral=True)

    try:
        embed_color = 0x00BFFF
        if color:
            color_clean = color.lstrip('#')
            if len(color_clean) == 6 and all(c in '0123456789ABCDEFabcdef' for c in color_clean):
                embed_color = int(color_clean, 16)

        embed = discord.Embed(
            title=titulo or "📨 Mensaje",
            description=mensaje,
            color=embed_color
        )

        images = [img for img in [imagen1, imagen2, imagen3, imagen4] if img]
        if images:
            embed.set_image(url=images[0])
            if len(images) > 1:
                embed.add_field(
                    name="🖼️ Imágenes adicionales",
                    value="\n".join([f"[Imagen {i+1}]({img})" for i, img in enumerate(images[1:])]),
                    inline=False
                )

        await canal.send(embed=embed)

        embed_success = discord.Embed(
            title="✅ Embed enviado",
            description=f"**Canal:** {canal.mention}\n**Imágenes:** {len(images)} cargadas\n**Título:** {titulo or 'Sin título'}",
            color=0x00FF00
        )
        await interaction.followup.send(embed=embed_success)

    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.followup.send(embed=embed)

# ---------- CREAR TICKETS ----------
@bot.tree.command(name="crear_tickets", description="Configurar sistema de tickets con botón")
@app_commands.describe(
    mensaje="Mensaje del ticket",
    emoji="Emoji para abrir ticket (ej: 🎫)",
    canal="Canal del panel",
    categoria="Categoría para tickets",
    descripcion="Canal para logs",
    imagen1="URL de imagen 1 (opcional)",
    imagen2="URL de imagen 2 (opcional)",
    imagen3="URL de imagen 3 (opcional)",
    imagen4="URL de imagen 4 (opcional)"
)
@commands.has_permissions(administrator=True)
async def slash_crear_tickets(
    interaction: discord.Interaction,
    mensaje: str,
    emoji: str,
    canal: discord.TextChannel,
    categoria: discord.CategoryChannel,
    descripcion: discord.TextChannel,
    imagen1: str = None,
    imagen2: str = None,
    imagen3: str = None,
    imagen4: str = None
):
    await interaction.response.defer(ephemeral=True)

    try:
        emoji_str = emoji.strip()
        if not emoji_str:
            embed = discord.Embed(title="❌ Error", description="Debes poner un emoji.", color=0xFF0000)
            await interaction.followup.send(embed=embed)
            return

        db.set_ticket_config(
            str(interaction.guild_id),
            mensaje,
            emoji_str,
            str(canal.id),
            str(categoria.id),
            str(descripcion.id),
            imagen1,
            imagen2,
            imagen3,
            imagen4
        )

        embed_ticket = discord.Embed(
            title="🎫 Sistema de Tickets",
            description=mensaje,
            color=0x00BFFF
        )
        
        images = [img for img in [imagen1, imagen2, imagen3, imagen4] if img]
        if images:
            embed_ticket.set_image(url=images[0])
            if len(images) > 1:
                embed_ticket.add_field(
                    name="🖼️ Imágenes adicionales",
                    value="\n".join([f"[Imagen {i+1}]({img})" for i, img in enumerate(images[1:])]),
                    inline=False
                )

        embed_ticket.add_field(
            name="📌 Abrir Ticket",
            value=f"Reacciona con {emoji_str} para abrir un ticket.",
            inline=False
        )

        view = OpenTicketButton(str(interaction.guild_id))
        await canal.send(embed=embed_ticket, view=view)

        embed_success = discord.Embed(
            title="✅ Ticket System Configurado",
            description=f"**Canal:** {canal.mention}\n**Categoría:** {categoria.mention}\n**Logs:** {descripcion.mention}\n**Emoji:** {emoji_str}\n\n**Imágenes:** {len(images)} cargadas",
            color=0x00FF00
        )
        await interaction.followup.send(embed=embed_success)

    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.followup.send(embed=embed)

# ---------- CONFIGURAR TICKETS (ALIAS) ----------
@bot.tree.command(name="configurar_tickets", description="Alias de /crear_tickets")
@app_commands.describe(
    mensaje="Mensaje del ticket",
    emoji="Emoji para abrir ticket",
    canal="Canal del panel",
    categoria="Categoría para tickets",
    descripcion="Canal para logs",
    imagen1="URL de imagen 1 (opcional)",
    imagen2="URL de imagen 2 (opcional)",
    imagen3="URL de imagen 3 (opcional)",
    imagen4="URL de imagen 4 (opcional)"
)
@commands.has_permissions(administrator=True)
async def slash_configurar_tickets(
    interaction: discord.Interaction,
    mensaje: str,
    emoji: str,
    canal: discord.TextChannel,
    categoria: discord.CategoryChannel,
    descripcion: discord.TextChannel,
    imagen1: str = None,
    imagen2: str = None,
    imagen3: str = None,
    imagen4: str = None
):
    await slash_crear_tickets(interaction, mensaje, emoji, canal, categoria, descripcion, imagen1, imagen2, imagen3, imagen4)

# ---------- ADD EMOJI ----------
@bot.tree.command(name="add_emoji", description="Robar un emoji de otro servidor")
@app_commands.describe(emoji="Pega el emoji que quieres robar (ej: <:rocky:123456789> o solo el ID)")
@commands.has_permissions(manage_emojis=True)
async def slash_add_emoji(interaction: discord.Interaction, emoji: str):
    await interaction.response.send_message("⏳ Descargando emoji...", ephemeral=True)
    
    try:
        emoji_input = emoji.strip()
        
        random_names = ["rocky", "store", "venta", "shop", "estrella", "luna", "sol", "nube", "fuego", "agua",
                       "tierra", "viento", "rayo", "trueno", "tormenta", "mar", "oceano", "playa", "arena",
                       "roca", "piedra", "gema", "diamante", "rubi", "esmeralda", "zafiro", "cristal", "metal",
                       "oro", "plata", "bronce", "hierro", "acero", "titanio", "neon", "laser", "feliz", "amor"]
        random_name = random.choice(random_names) + str(random.randint(100, 999))

        emoji_id = None
        is_animated = False
        original_name = ""

        if emoji_input.startswith('<') and emoji_input.endswith('>'):
            match = re.match(r'<a?:([^:]+):(\d+)>', emoji_input)
            if match:
                original_name = match.group(1)
                emoji_id = int(match.group(2))
                is_animated = emoji_input.startswith('<a:')
        elif emoji_input.isdigit():
            emoji_id = int(emoji_input)
        
        if emoji_id:
            ext = "gif" if is_animated else "png"
            emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?v=1"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(emoji_url) as resp:
                    if resp.status == 200:
                        image_data = await resp.read()
                        new_emoji = await interaction.guild.create_custom_emoji(
                            name=random_name,
                            image=image_data
                        )
                        embed = discord.Embed(
                            title="✅ Emoji robado con éxito",
                            description=f"**Nuevo:** `:{new_emoji.name}:`\n**Original:** `{original_name or emoji_input}`\n**ID:** `{emoji_id}`",
                            color=0x00FF00
                        )
                        await interaction.edit_original_response(content=None, embed=embed)
                        return
                    else:
                        embed = discord.Embed(
                            title="❌ No se pudo robar el emoji",
                            description=f"No se pudo descargar el emoji. Verifica el ID `{emoji_id}`",
                            color=0xFF0000
                        )
                        await interaction.edit_original_response(content=None, embed=embed)
                        return
        
        embed = discord.Embed(
            title="📌 Cómo robar un emoji",
            description="**1.** Copia el emoji de otro servidor\n"
                        "**2.** Pega aquí: `/add_emoji <:nombre:id>`\n\n"
                        "**Ejemplo:** `/add_emoji <:rocky:123456789>`\n"
                        "**Emojis animados:** `<a:nombre:id>`\n"
                        "**Solo ID:** `/add_emoji 123456789`",
            color=0x00BFFF
        )
        await interaction.edit_original_response(content=None, embed=embed)

    except discord.Forbidden:
        embed = discord.Embed(
            title="❌ Permiso denegado",
            description="No tengo permiso para crear emojis en este servidor.",
            color=0xFF0000
        )
        await interaction.edit_original_response(content=None, embed=embed)
    except Exception as e:
        embed = discord.Embed(
            title="❌ Error",
            description=f"{str(e)}\n\n**Formato correcto:** `<:nombre:id>` o `<a:nombre:id>`",
            color=0xFF0000
        )
        await interaction.edit_original_response(content=None, embed=embed)

# ---------- REGALO ----------
@bot.tree.command(name="regalo", description="Abrir regalo (24h cooldown)")
async def slash_regalo(interaction: discord.Interaction):
    await interaction.response.defer()
    user_id = str(interaction.user.id)
    if not db.can_open_gift(user_id):
        embed = discord.Embed(title="❌ Cooldown", description="Espera 24 horas.", color=0xFF0000)
        await interaction.followup.send(embed=embed)
        return
    gift_types = ["🎁 Caja Misteriosa", "✨ Estrella Rara", "🪙 Bolsa de Monedas", "💎 Fragmento de Cristal", "🌀 Vórtice Temporal"]
    gift_contents = ["+10 Horas de Exploración", "+5 Bonus", "Insignia", "Rol Personalizado"]
    gift_type = random.choice(gift_types)
    content = random.choice(gift_contents)
    gift_id = db.add_gift(user_id, gift_type, content)
    db.set_gift_cooldown(user_id, GIFT_COOLDOWN_HOURS)
    bonus = random.randint(1, 10)
    db.update_user_exploration(user_id, bonus)
    embed = discord.Embed(title="🎉 ¡Regalo!", description=f"**{gift_type}**\n{content}\n\n✨ +{bonus} Exploración\n📦 ID: `{gift_id}`", color=0xFFD700)
    await interaction.followup.send(embed=embed)

# ---------- ONDA ----------
@bot.tree.command(name="onda", description="Enviar onda")
@app_commands.describe(usuario="Usuario")
async def slash_onda(interaction: discord.Interaction, usuario: discord.Member):
    await interaction.response.defer()
    if usuario.id == interaction.user.id:
        embed = discord.Embed(title="❌ Error", description="No puedes enviarte onda a ti mismo.", color=0xFF0000)
        await interaction.followup.send(embed=embed)
        return
    db.record_wave(str(interaction.user.id), str(usuario.id))
    embed = discord.Embed(title="🌊 ¡Onda!", description=f"{interaction.user.mention} → {usuario.mention}!", color=0x00BFFF)
    await interaction.followup.send(embed=embed)

# ---------- TABLA ----------
@bot.tree.command(name="tabla", description="Clasificación")
async def slash_tabla(interaction: discord.Interaction):
    await interaction.response.defer()
    users = db.get_leaderboard(10)
    if not users:
        embed = discord.Embed(title="📊 Tabla", description="No hay usuarios.", color=0x00BFFF)
        await interaction.followup.send(embed=embed)
        return
    desc = "\n".join([f"#{i+1} **{u['username']}** - {u['score']} pts" for i, u in enumerate(users)])
    embed = discord.Embed(title="🏆 Tabla", description=desc, color=0xFFD700)
    await interaction.followup.send(embed=embed)

# ---------- PERFIL ----------
@bot.tree.command(name="perfil", description="Ver perfil")
@app_commands.describe(usuario="Usuario")
async def slash_perfil(interaction: discord.Interaction, usuario: discord.Member = None):
    await interaction.response.defer()
    target = usuario or interaction.user
    user_data = db.get_user(str(target.id))
    if not user_data:
        embed = discord.Embed(title="❌ Error", description="Usuario no encontrado.", color=0xFF0000)
        await interaction.followup.send(embed=embed)
        return
    embed = discord.Embed(title=f"👤 {target.display_name}", description=f"**Referencias:** {user_data['total_references_generated']}\n**Exploración:** {user_data['exploration_hours']}h\n**Regalos:** {user_data['gifts_opened']}", color=0x00BFFF)
    embed.set_thumbnail(url=target.display_avatar.url)
    await interaction.followup.send(embed=embed)

# ============================================================
# MODERACIÓN
# ============================================================

@bot.tree.command(name="banear", description="Banear")
@app_commands.describe(usuario="Usuario", razon="Razón")
@commands.has_permissions(ban_members=True)
async def slash_banear(interaction: discord.Interaction, usuario: discord.Member, razon: str = "Sin razón"):
    try:
        await usuario.ban(reason=razon)
        embed = discord.Embed(title="✅ Baneado", description=f"{usuario.mention}\nRazón: {razon}", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="expulsar", description="Expulsar")
@app_commands.describe(usuario="Usuario", razon="Razón")
@commands.has_permissions(kick_members=True)
async def slash_expulsar(interaction: discord.Interaction, usuario: discord.Member, razon: str = "Sin razón"):
    try:
        await usuario.kick(reason=razon)
        embed = discord.Embed(title="✅ Expulsado", description=f"{usuario.mention}\nRazón: {razon}", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="silenciar", description="Silenciar")
@app_commands.describe(usuario="Usuario", duracion="Duración (1h, 30m)", razon="Razón")
@commands.has_permissions(manage_roles=True)
async def slash_silenciar(interaction: discord.Interaction, usuario: discord.Member, duracion: str = "1h", razon: str = "Sin razón"):
    try:
        units = {'s':1, 'm':60, 'h':3600, 'd':86400}
        unit = duracion[-1]
        seconds = int(duracion[:-1]) * units.get(unit, 3600)
        until = datetime.utcnow() + timedelta(seconds=seconds)
        db.add_mute(str(usuario.id), str(interaction.guild_id), until, razon)
        muted_role = discord.utils.get(interaction.guild.roles, name="Silenciado")
        if not muted_role:
            muted_role = await interaction.guild.create_role(name="Silenciado")
            for channel in interaction.guild.channels:
                try:
                    await channel.set_permissions(muted_role, send_messages=False, add_reactions=False, connect=False)
                except:
                    pass
        await usuario.add_roles(muted_role, reason=f"Silenciado: {razon}")
        embed = discord.Embed(title="✅ Silenciado", description=f"{usuario.mention} por {duracion}\nRazón: {razon}", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="desilenciar", description="Desilenciar")
@app_commands.describe(usuario="Usuario")
@commands.has_permissions(manage_roles=True)
async def slash_desilenciar(interaction: discord.Interaction, usuario: discord.Member):
    try:
        db.remove_mute(str(usuario.id), str(interaction.guild_id))
        muted_role = discord.utils.get(interaction.guild.roles, name="Silenciado")
        if muted_role:
            await usuario.remove_roles(muted_role, reason="Desilenciado")
        embed = discord.Embed(title="✅ Desilenciado", description=f"{usuario.mention}", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="limpiar", description="Eliminar mensajes")
@app_commands.describe(cantidad="1-100")
@commands.has_permissions(manage_messages=True)
async def slash_limpiar(interaction: discord.Interaction, cantidad: int):
    if cantidad < 1 or cantidad > 100:
        embed = discord.Embed(title="❌ Error", description="Entre 1 y 100.", color=0xFF0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    try:
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=cantidad)
        embed = discord.Embed(title="✅ Eliminados", description=f"{len(deleted)} mensajes.", color=0x00FF00)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="bloquear", description="Bloquear canal")
@commands.has_permissions(manage_channels=True)
async def slash_bloquear(interaction: discord.Interaction):
    try:
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
        embed = discord.Embed(title="🔒 Bloqueado", description=f"{interaction.channel.mention}", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="desbloquear", description="Desbloquear canal")
@commands.has_permissions(manage_channels=True)
async def slash_desbloquear(interaction: discord.Interaction):
    try:
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
        embed = discord.Embed(title="🔓 Desbloqueado", description=f"{interaction.channel.mention}", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

# ============================================================
# ADMIN
# ============================================================

@bot.tree.command(name="rol_auto", description="Rol automático")
@app_commands.describe(rol="Rol")
@commands.has_permissions(administrator=True)
async def slash_rol_auto(interaction: discord.Interaction, rol: discord.Role):
    try:
        db.set_autorole(str(interaction.guild_id), str(rol.id))
        embed = discord.Embed(title="✅ Rol Auto", description=f"{rol.mention}", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="color", description="Cambiar color")
@app_commands.describe(hex="Código hex")
@commands.has_permissions(manage_roles=True)
async def slash_color(interaction: discord.Interaction, hex: str):
    try:
        color = int(hex.lstrip('#'), 16)
        await interaction.user.edit(color=discord.Color(color))
        embed = discord.Embed(title="✅ Color", description=f"`{hex}`", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="avatar", description="Cambiar avatar")
@app_commands.describe(url="URL")
async def slash_avatar(interaction: discord.Interaction, url: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    await interaction.user.edit(avatar=await resp.read())
                    embed = discord.Embed(title="✅ Avatar", description="Actualizado", color=0x00FF00)
                    await interaction.response.send_message(embed=embed)
                else:
                    embed = discord.Embed(title="❌ Error", description="No se pudo descargar.", color=0xFF0000)
                    await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="id_usuario", description="ID de usuario")
@app_commands.describe(usuario="Usuario")
async def slash_id_usuario(interaction: discord.Interaction, usuario: discord.Member = None):
    target = usuario or interaction.user
    embed = discord.Embed(title="🆔 ID", description=f"{target.mention}\n`{target.id}`", color=0x00BFFF)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="autor", description="Mensaje de autor")
@app_commands.describe(texto="Texto")
@commands.has_permissions(manage_messages=True)
async def slash_autor(interaction: discord.Interaction, texto: str):
    embed = discord.Embed(title="✍️ Autor", description=f"**{interaction.user.display_name}**\n{texto}", color=0x00BFFF)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="instagram", description="Instagram")
@app_commands.describe(url="URL")
async def slash_instagram(interaction: discord.Interaction, url: str):
    try:
        db.set_social_link(str(interaction.user.id), "instagram", url)
        embed = discord.Embed(title="✅ Instagram", description=url, color=0x00FF00)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="tiktok", description="TikTok")
@app_commands.describe(url="URL")
async def slash_tiktok(interaction: discord.Interaction, url: str):
    try:
        db.set_social_link(str(interaction.user.id), "tiktok", url)
        embed = discord.Embed(title="✅ TikTok", description=url, color=0x00FF00)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="unirse", description="Unirse a voz 24/7")
async def slash_unirse(interaction: discord.Interaction):
    try:
        if not interaction.user.voice:
            embed = discord.Embed(title="❌ Error", description="No estás en un canal de voz.", color=0xFF0000)
            await interaction.response.send_message(embed=embed)
            return
        channel = interaction.user.voice.channel
        if interaction.guild.id in bot.vc_data:
            await bot.vc_data[interaction.guild.id].move_to(channel)
        else:
            vc = await channel.connect()
            bot.vc_data[interaction.guild.id] = vc
        embed = discord.Embed(title="🔊 Conectado", description=f"{channel.mention} (24/7)", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="salir", description="Salir de voz")
async def slash_salir(interaction: discord.Interaction):
    try:
        if interaction.guild.id in bot.vc_data:
            await bot.vc_data[interaction.guild.id].disconnect()
            del bot.vc_data[interaction.guild.id]
            embed = discord.Embed(title="🔇 Desconectado", description="Salí del canal.", color=0x00FF00)
            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(title="❌ Error", description="No estoy en un canal.", color=0xFF0000)
            await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="antiraid", description="Antiraid")
@commands.has_permissions(administrator=True)
async def slash_antiraid(interaction: discord.Interaction):
    try:
        await interaction.channel.set_permissions(interaction.guild.default_role, create_instant_invite=False, change_nickname=False)
        embed = discord.Embed(title="🛡️ Antiraid", description="Activado", color=0x00FF00)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=str(e), color=0xFF0000)
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="crear_trigger", description="Trigger de pago")
@app_commands.describe(prefijo="Prefijo (ej: !pagar)", mensaje="Mensaje")
@commands.has_permissions(administrator=True)
async def slash_crear_trigger(interaction: discord.Interaction, prefijo: str, mensaje: str):
    await interaction.response.defer(ephemeral=True)
    if not prefijo.startswith('!'):
        prefijo = '!' + prefijo
    success = db.create_payment_trigger(str(interaction.guild_id), prefijo, mensaje, str(interaction.user.id))
    if success:
        embed = discord.Embed(title="✅ Trigger", description=f"`{prefijo}`", color=0x00FF00)
    else:
        embed = discord.Embed(title="❌ Error", description="Ya existe.", color=0xFF0000)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="configurar_auto", description="Auto-respuesta")
@app_commands.describe(canal="Canal", mensaje="Respuesta", incluir="Incluir original")
@commands.has_permissions(administrator=True)
async def slash_configurar_auto(interaction: discord.Interaction, canal: discord.TextChannel, mensaje: str, incluir: bool = False):
    await interaction.response.defer(ephemeral=True)
    success = db.create_auto_reply(str(interaction.guild_id), str(canal.id), mensaje, str(interaction.user.id), incluir)
    if success:
        embed = discord.Embed(title="✅ Auto-Reply", description=f"{canal.mention}", color=0x00FF00)
    else:
        embed = discord.Embed(title="❌ Error", description="Falló.", color=0xFF0000)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="listar_configs", description="Listar configs")
@app_commands.describe(tipo="payments o refes")
@commands.has_permissions(administrator=True)
async def slash_listar_configs(interaction: discord.Interaction, tipo: str):
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild_id)
    if tipo.lower() == 'payments':
        items = db.list_payment_triggers(guild_id)
        if not items:
            embed = discord.Embed(title="📋 Sin triggers", description="Ninguno.", color=0x00BFFF)
            await interaction.followup.send(embed=embed)
            return
        embed = discord.Embed(title="💳 Triggers", color=0x00BFFF)
        for t in items:
            embed.add_field(name=t['prefix'], value=t['message'][:50], inline=False)
        await interaction.followup.send(embed=embed)
    elif tipo.lower() == 'refes':
        items = db.list_auto_replies(guild_id)
        if not items:
            embed = discord.Embed(title="📋 Sin auto-respuestas", description="Ninguna.", color=0x00BFFF)
            await interaction.followup.send(embed=embed)
            return
        embed = discord.Embed(title="🔁 Auto-Respuestas", color=0x00BFFF)
        for t in items:
            embed.add_field(name=f"<#{t['channel_id']}>", value=t['message'][:50], inline=False)
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="eliminar_config", description="Eliminar config")
@app_commands.describe(tipo="payment o refe", id="ID o prefijo")
@commands.has_permissions(administrator=True)
async def slash_eliminar_config(interaction: discord.Interaction, tipo: str, id: str):
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild_id)
    if tipo.lower() == 'payment':
        if not id.startswith('!'):
            id = '!' + id
        success = db.delete_payment_trigger(guild_id, id)
        embed = discord.Embed(title="✅ Eliminado", description=f"`{id}`", color=0x00FF00) if success else discord.Embed(title="❌ Error", description="No encontrado.", color=0xFF0000)
    elif tipo.lower() == 'refe':
        channel_id = re.sub(r'[<#>]', '', id)
        success = db.delete_auto_reply(guild_id, channel_id)
        embed = discord.Embed(title="✅ Eliminado", description=f"<#{channel_id}>", color=0x00FF00) if success else discord.Embed(title="❌ Error", description="No encontrado.", color=0xFF0000)
    else:
        embed = discord.Embed(title="❌ Error", description="Tipo inválido.", color=0xFF0000)
    await interaction.followup.send(embed=embed)

# ============================================================
# WORDLE
# ============================================================

WORDLE_WORDS = ["apple", "brain", "crane", "dance", "eagle", "flame", "grape", "heart", "image", "joker", "knife", "lemon", "mango", "night", "ocean", "piano", "queen", "river", "stone", "tiger", "umbra", "vivid", "water", "xenon", "youth", "zebra", "aback", "abase", "abate", "abbey", "abbot", "abhor", "abide", "abled", "abode", "abort", "about", "above", "abuse", "abyss", "acorn", "acrid", "actor", "acute", "adage", "adapt", "adept", "admin", "admit", "adobe", "adopt", "adore", "adorn", "adult", "affix", "afire", "afoot", "afoul", "after", "again", "agape", "agate", "agent", "agile", "aging", "aglow", "agony", "agree", "ahead", "aider", "aisle", "alarm", "album", "alert", "algae", "alibi", "alien", "align", "alike", "alive", "allay", "alley", "allot", "allow", "alloy", "aloft", "alone", "along", "aloof", "aloud", "alpha", "altar", "alter", "amass", "amaze", "amber", "amble", "amend", "amiss", "amity", "among", "ample", "amply", "amuse", "angel", "anger", "angle", "angry", "angst", "anime", "ankle", "annex", "annoy", "annul", "anode", "antic", "anvil", "aorta", "apart", "aphid", "aping", "apnea", "apply", "apron", "aptly", "arbor", "ardor", "arena", "argue", "arise", "armor", "aroma", "arose", "array", "arrow", "arson", "artsy", "ascot", "ashen", "aside", "askew", "assay", "asset", "atoll", "atone", "attic", "audio", "audit", "avail", "avert", "avian", "avoid", "await", "awake", "award", "aware", "awash", "awful", "awoke", "axial", "axiom", "axion", "azure", "bacon", "badge", "badly", "baffle", "bagel", "baggy"]

def get_wordle_answer() -> str:
    return random.choice(WORDLE_WORDS)

def get_wordle_emoji(guess: str, answer: str) -> str:
    result = ""
    answer_list = list(answer)
    guess_list = list(guess)
    used = [False] * len(answer)
    for i in range(5):
        if guess_list[i] == answer_list[i]:
            result += "🟩"
            used[i] = True
            guess_list[i] = None
    for i in range(5):
        if guess_list[i] is not None:
            found = False
            for j in range(5):
                if not used[j] and guess_list[i] == answer_list[j]:
                    found = True
                    used[j] = True
                    break
            if found:
                result += "🟨"
            else:
                result += "⬛"
    return result

@bot.tree.command(name="wordle", description="Iniciar Wordle")
async def slash_wordle(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    existing = db.get_wordle_game(user_id)
    if existing and existing['status'] == "playing":
        embed = discord.Embed(title="🎮 Wordle", description=f"Juego activo. Intentos: {existing['attempts']}/6", color=0x00BFFF)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    answer = get_wordle_answer()
    db.create_wordle_game(user_id, answer)
    embed = discord.Embed(title="🎮 Wordle", description="Adivina la palabra de 5 letras. Usa /wordle_guess", color=0x00BFFF)
    embed.add_field(name="📝", value="🟩 Correcta\n🟨 Letra correcta, posición no\n⬛ Incorrecta", inline=False)
    embed.add_field(name="🔢", value="0/6", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="wordle_guess", description="Adivinar")
@app_commands.describe(palabra="5 letras")
async def slash_wordle_guess(interaction: discord.Interaction, palabra: str):
    user_id = str(interaction.user.id)
    palabra = palabra.lower().strip()
    if len(palabra) != 5:
        embed = discord.Embed(title="❌ Error", description="5 letras exactas.", color=0xFF0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    if not palabra.isalpha():
        embed = discord.Embed(title="❌ Error", description="Solo letras.", color=0xFF0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    game = db.get_wordle_game(user_id)
    if not game or game['status'] != "playing":
        embed = discord.Embed(title="🎮 Wordle", description="Usa /wordle primero.", color=0x00BFFF)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    answer = game['answer']
    guesses = json.loads(game['guesses'])
    attempts = game['attempts'] + 1
    guesses.append(palabra)
    won = (palabra == answer)
    status = "won" if won else ("lost" if attempts >= 6 else "playing")
    db.update_wordle_game(user_id, guesses, attempts, status)
    embed = discord.Embed(color=0x00FF00 if won else (0xFF0000 if status == "lost" else 0x00BFFF))
    guess_display = ""
    for g in guesses:
        guess_display += f"`{g.upper()}` {get_wordle_emoji(g, answer)}\n"
    embed.description = guess_display
    embed.add_field(name="🔢", value=f"{attempts}/6", inline=True)
    if won:
        embed.title = "🎉 Ganaste!"
        embed.description += f"\n✅ {answer.upper()}"
        db.update_wordle_score(user_id, True, attempts)
        db.delete_wordle_game(user_id)
    elif status == "lost":
        embed.title = "😔 Perdiste"
        embed.description += f"\n❌ {answer.upper()}"
        db.update_wordle_score(user_id, False, attempts)
        db.delete_wordle_game(user_id)
    else:
        embed.title = f"🎮 Wordle • {attempts}/6"
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="wordle_stats", description="Estadísticas Wordle")
async def slash_wordle_stats(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    stats = db.get_wordle_score(user_id)
    embed = discord.Embed(title=f"📊 {interaction.user.display_name}", color=0x00BFFF)
    embed.add_field(name="Partidas", value=stats['games_played'], inline=True)
    embed.add_field(name="Ganadas", value=stats['games_won'], inline=True)
    embed.add_field(name="Tasa", value=f"{round(stats['games_won']/stats['games_played']*100 if stats['games_played'] > 0 else 0)}%", inline=True)
    embed.add_field(name="Racha actual", value=stats['current_streak'], inline=True)
    embed.add_field(name="Racha máxima", value=stats['max_streak'], inline=True)
    embed.add_field(name="Intentos", value=f"{round(stats['total_guesses']/stats['games_won'] if stats['games_won'] > 0 else 0, 1)}", inline=True)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)