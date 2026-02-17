import sqlite3
from contextlib import contextmanager
from datetime import datetime
import os
import json

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")

def get_db_path():
    """Получить путь к базе данных"""
    if DATABASE_URL.startswith("sqlite:///"):
        return DATABASE_URL.replace("sqlite:///", "")
    return "./data/app.db"

@contextmanager
def get_db():
    """Контекстный менеджер для работы с базой данных"""
    db_path = get_db_path()
    # Создаем директорию если нужно
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Инициализация базы данных"""
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    with get_db() as db:
        # Таблица пользователей
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                segment TEXT DEFAULT 'new',
                total_spent REAL DEFAULT 0,
                interests TEXT, -- JSON array
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица событий
        db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                product_id TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                properties TEXT, -- JSON
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        
        # Таблица сообщений
        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                message_type TEXT NOT NULL,
                subject TEXT,
                content TEXT NOT NULL,
                status TEXT DEFAULT 'pending', -- pending, sent, delivered, failed
                sent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        
        # Таблица промптов
        db.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                template TEXT NOT NULL,
                description TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица конфигурации
        db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Индексы
        db.execute("CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status)")
        
        # Добавляем дефолтные промпты если их нет
        default_prompts = [
            ("decision_agent", """Ты — AI-агент по персонализации коммуникаций с клиентами интернет-магазина.

**Контекст:**
- Пользователь: {user_profile}
- Только что произошло событие: {event}
- История взаимодействий за последние 24 часа: {recent_activity}

**Твоя задача:**
Проанализируй ситуацию и реши, нужно ли отправить клиенту персонализированное сообщение. Если да — выбери тип сообщения, канал и сгенерируй текст.

**Инструменты, которые у тебя есть:**
1. send_email(recipient, subject, body) — отправить email
2. send_push(user_id, title, body) — отправить push-уведомление
3. get_recommendations(user_id, category) — получить рекомендации товаров
4. get_user_profile(user_id) — получить полный профиль

**Правила:**
- Не отправляй больше 1 сообщения в час одному пользователю
- Для VIP-клиентов (покупки > 10000 руб) можно делать исключение
- Избегай навязчивости: если пользователь только что зашёл, не пиши сразу

**Формат ответа (строго JSON):**
{{
  "should_engage": true/false,
  "reasoning": "краткое объяснение почему",
  "action": {{
    "type": "email" или "push" или null,
    "subject": "тема если email",
    "body": "текст сообщения",
    "recommendations": ["product1", "product2"]
  }}
}}""", "Базовый промт для агента принятия решений"),
            
            ("text_generator", """Ты — профессиональный копирайтер, специализирующийся на персонализированных email-рассылках и push-уведомлениях.

**Данные о клиенте:**
- Имя: {name}
- Интересы: {interests}
- Последние просмотры: {recent_views}
- История покупок: {purchase_history}
- Сегмент: {segment}

**Задача:**
Напиши короткое персонализированное сообщение для {channel} (email/push) на русском языке.

**Условия:**
- Email: до 150 слов, дружелюбный тон
- Push: до 80 символов, ёмко
- Упомяни конкретные товары
- Добавь призыв к действию

**Тон коммуникации:**
- Для новых клиентов: приветственный, обучающий
- Для постоянных: благодарственный, эксклюзивный
- Для VIP: персональный
- Для спящих: возвращающий, с выгодным предложением

**Твой ответ (только текст сообщения):**""", "Промт для генерации текста сообщения"),
            
            ("quality_checker", """Ты — строгий редактор, проверяющий сообщения перед отправкой клиентам.

**Исходное сообщение:**
{message}

**Контекст клиента:**
{user_context}

**Проверь по критериям (оценка от 0 до 1):**
1. Грамматика и орфография
2. Тон — соответствует ли бренду
3. Персонализация
4. Релевантность
5. Навязчивость
6. Этичность

**Формат ответа JSON:**
{{
  "overall_score": 0.85,
  "criteria_scores": {{
    "grammar": 0.9,
    "tone": 0.8,
    "personalization": 0.7,
    "relevance": 0.9,
    "spam_score": 0.2,
    "ethics": 1.0
  }},
  "approved": true/false,
  "comments": "замечания",
  "suggested_improvement": "улучшенная версия"
}}""", "Промт для проверки качества сообщений")
        ]
        
        for name, template, description in default_prompts:
            try:
                db.execute(
                    "INSERT INTO prompts (name, template, description) VALUES (?, ?, ?)",
                    (name, template, description)
                )
            except sqlite3.IntegrityError:
                pass  # Промт уже существует
        
        db.commit()
        
        print(f"Database initialized at {db_path}")
