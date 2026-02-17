from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import json
import os
import sqlite3
from contextlib import contextmanager
import httpx
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.models import init_db, get_db
from app.agent import PersonalizationAgent
from app.config import settings

app = FastAPI(title="AI Agent Personalization", version="1.0.0")

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Templates and static files
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Initialize agent
agent = PersonalizationAgent()

class Event(BaseModel):
    user_id: str
    event: str
    product_id: Optional[str] = None
    timestamp: datetime
    properties: Dict = {}

class UserProfile(BaseModel):
    user_id: str
    name: str
    email: Optional[str] = None
    segment: str = "new"
    total_spent: float = 0
    interests: List[str] = []

class MessageRequest(BaseModel):
    user_id: str
    message_type: str  # email, push, sms
    subject: Optional[str] = None
    content: str

class AdminLogin(BaseModel):
    username: str
    password: str

class PromptTemplate(BaseModel):
    name: str
    template: str
    description: str

# JWT Token functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=24)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt

async def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication")

# API Endpoints
@app.post("/api/event")
async def handle_event(event: Event):
    """Обработка события от пользователя"""
    with get_db() as db:
        # Сохраняем событие
        db.execute(
            """INSERT INTO events (user_id, event_type, product_id, timestamp, properties)
               VALUES (?, ?, ?, ?, ?)""",
            (event.user_id, event.event, event.product_id, event.timestamp, json.dumps(event.properties))
        )
        db.commit()
        
        # Получаем профиль пользователя
        cursor = db.execute("SELECT * FROM users WHERE user_id = ?", (event.user_id,))
        user_row = cursor.fetchone()
        
        if not user_row:
            # Создаем нового пользователя
            db.execute(
                "INSERT INTO users (user_id, name, segment, total_spent, created_at) VALUES (?, ?, ?, ?, ?)",
                (event.user_id, f"User_{event.user_id}", "new", 0, datetime.now())
            )
            db.commit()
            user_profile = {"user_id": event.user_id, "name": f"User_{event.user_id}", "segment": "new", "total_spent": 0}
        else:
            user_profile = dict(user_row)
        
        # Получаем недавнюю активность
        recent_events = db.execute(
            """SELECT * FROM events 
               WHERE user_id = ? AND timestamp > datetime('now', '-24 hours')
               ORDER BY timestamp DESC LIMIT 10""",
            (event.user_id,)
        ).fetchall()
        
        recent_activity = [dict(e) for e in recent_events]
        
        # Вызываем агента
        result = agent.make_decision(user_profile, event.dict(), recent_activity)
        
        # Если нужно отправить сообщение
        if result.get("should_engage") and result.get("action", {}).get("type"):
            action = result["action"]
            # Сохраняем сообщение в базу
            db.execute(
                """INSERT INTO messages (user_id, message_type, subject, content, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (event.user_id, action["type"], action.get("subject", ""), action.get("body", ""), 
                 "pending", datetime.now())
            )
            db.commit()
            
            # Отправляем сообщение
            if action["type"] == "email":
                await send_email(event.user_id, action.get("subject", ""), action.get("body", ""))
            elif action["type"] == "push":
                await send_push(event.user_id, action.get("body", ""))
        
        return {"status": "processed", "agent_decision": result}

@app.get("/api/users/{user_id}")
async def get_user(user_id: str, admin: str = Depends(get_current_admin)):
    """Получить профиль пользователя"""
    with get_db() as db:
        cursor = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return dict(user)

@app.get("/api/users/{user_id}/events")
async def get_user_events(user_id: str, admin: str = Depends(get_current_admin)):
    """Получить историю событий пользователя"""
    with get_db() as db:
        cursor = db.execute(
            "SELECT * FROM events WHERE user_id = ? ORDER BY timestamp DESC",
            (user_id,)
        )
        events = cursor.fetchall()
        return [dict(e) for e in events]

@app.get("/api/users/{user_id}/messages")
async def get_user_messages(user_id: str, admin: str = Depends(get_current_admin)):
    """Получить историю сообщений пользователя"""
    with get_db() as db:
        cursor = db.execute(
            "SELECT * FROM messages WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        messages = cursor.fetchall()
        return [dict(m) for m in messages]

@app.post("/api/admin/login")
async def admin_login(login: AdminLogin):
    """Вход в админку"""
    # Простая проверка - в продакшене используйте хеширование
    if login.username == settings.ADMIN_USERNAME and login.password == settings.ADMIN_PASSWORD:
        access_token = create_access_token(data={"sub": login.username})
        return {"access_token": access_token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Incorrect username or password")

@app.get("/api/admin/dashboard")
async def admin_dashboard(admin: str = Depends(get_current_admin)):
    """Статистика для дашборда"""
    with get_db() as db:
        total_users = db.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
        total_events = db.execute("SELECT COUNT(*) as count FROM events").fetchone()["count"]
        total_messages = db.execute("SELECT COUNT(*) as count FROM messages").fetchone()["count"]
        pending_messages = db.execute(
            "SELECT COUNT(*) as count FROM messages WHERE status = 'pending'"
        ).fetchone()["count"]
        
        recent_events = db.execute(
            """SELECT * FROM events 
               WHERE timestamp > datetime('now', '-24 hours')
               ORDER BY timestamp DESC LIMIT 10"""
        ).fetchall()
        
        return {
            "total_users": total_users,
            "total_events": total_events,
            "total_messages": total_messages,
            "pending_messages": pending_messages,
            "recent_events": [dict(e) for e in recent_events]
        }

@app.get("/api/admin/prompts")
async def get_prompts(admin: str = Depends(get_current_admin)):
    """Получить список промптов"""
    with get_db() as db:
        cursor = db.execute("SELECT * FROM prompts ORDER BY created_at DESC")
        prompts = cursor.fetchall()
        return [dict(p) for p in prompts]

@app.post("/api/admin/prompts")
async def create_prompt(prompt: PromptTemplate, admin: str = Depends(get_current_admin)):
    """Создать новый промпт"""
    with get_db() as db:
        db.execute(
            """INSERT INTO prompts (name, template, description, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (prompt.name, prompt.template, prompt.description, datetime.now(), datetime.now())
        )
        db.commit()
        return {"status": "created"}

@app.put("/api/admin/prompts/{prompt_id}")
async def update_prompt(prompt_id: int, prompt: PromptTemplate, admin: str = Depends(get_current_admin)):
    """Обновить промпт"""
    with get_db() as db:
        db.execute(
            """UPDATE prompts SET name = ?, template = ?, description = ?, updated_at = ?
               WHERE id = ?""",
            (prompt.name, prompt.template, prompt.description, datetime.now(), prompt_id)
        )
        db.commit()
        return {"status": "updated"}

@app.get("/api/admin/messages")
async def get_all_messages(admin: str = Depends(get_current_admin)):
    """Получить все сообщения"""
    with get_db() as db:
        cursor = db.execute(
            "SELECT * FROM messages ORDER BY created_at DESC LIMIT 100"
        )
        messages = cursor.fetchall()
        return [dict(m) for m in messages]

# Web Interface
@app.get("/", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """Страница входа в админку"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page(request: Request):
    """Главная страница админки"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    """Страница пользователей"""
    return templates.TemplateResponse("users.html", {"request": request})

@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request):
    """Страница событий"""
    return templates.TemplateResponse("events.html", {"request": request})

@app.get("/messages", response_class=HTMLResponse)
async def messages_page(request: Request):
    """Страница сообщений"""
    return templates.TemplateResponse("messages.html", {"request": request})

@app.get("/prompts", response_class=HTMLResponse)
async def prompts_page(request: Request):
    """Страница управления промптами"""
    return templates.TemplateResponse("prompts.html", {"request": request})

# Helper functions
async def send_email(user_id: str, subject: str, body: str):
    """Отправка email (заглушка)"""
    print(f"[EMAIL] To {user_id}: {subject}")
    print(f"[EMAIL] Body: {body[:100]}...")
    # Здесь интеграция с реальным email-сервисом

async def send_push(user_id: str, message: str):
    """Отправка push-уведомления (заглушка)"""
    print(f"[PUSH] To {user_id}: {message}")
    # Здесь интеграция с Firebase Cloud Messaging или аналогом

# Startup event
@app.on_event("startup")
async def startup_event():
    init_db()
    print("Database initialized")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
