# AI Agent Personalization

AI-агент для персонализации коммуникаций с клиентами интернет-магазина на базе LLM.

## Возможности

- 🤖 Автоматическая обработка событий пользователей
- 📧 Генерация персонализированных email и push-уведомлений
- 🎯 Интеллектуальное принятие решений на основе поведения
- 📊 Админ-панель для управления всем пайплайном
- 📝 Управление промптами через UI
- 🔐 JWT-аутентификация

## Архитектура

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Client        │────▶│   FastAPI       │────▶│   SQLite        │
│   Events        │     │   AI Agent      │     │   Database      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │   OpenAI API    │
                        │   (LLM)         │
                        └─────────────────┘
```

## Быстрый старт

### Локальный запуск

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/ai-agent-personalization.git
cd ai-agent-personalization
```

2. Создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Создайте файл `.env`:
```bash
cp .env.example .env
# Отредактируйте .env и добавьте ваш OPENAI_API_KEY
```

5. Запустите приложение:
```bash
uvicorn app.main:app --reload
```

6. Откройте админ-панель: http://localhost:8000

### Деплой на Render

1. Создайте новый Web Service на Render
2. Подключите GitHub репозиторий
3. Render автоматически использует `render.yaml` для конфигурации
4. Добавьте переменные окружения:
   - `OPENAI_API_KEY` - ваш ключ API OpenAI
   - `ADMIN_PASSWORD` - пароль для админ-панели

## API Endpoints

### События
- `POST /api/event` - Отправить событие от пользователя

### Пользователи
- `GET /api/users/{user_id}` - Получить профиль пользователя
- `GET /api/users/{user_id}/events` - История событий
- `GET /api/users/{user_id}/messages` - История сообщений

### Админка
- `POST /api/admin/login` - Вход в админку
- `GET /api/admin/dashboard` - Статистика
- `GET /api/admin/prompts` - Список промптов
- `POST /api/admin/prompts` - Создать промпт
- `PUT /api/admin/prompts/{id}` - Обновить промпт
- `GET /api/admin/messages` - Все сообщения

## Пример использования

```python
import requests

# Отправка события
event = {
    "user_id": "12345",
    "event": "cart_added",
    "product_id": "drone-x100",
    "timestamp": "2026-02-17T10:30:00",
    "properties": {
        "price": 599.99,
        "category": "drones"
    }
}

response = requests.post("http://localhost:8000/api/event", json=event)
print(response.json())
```

## Структура проекта

```
.
├── app/
│   ├── __init__.py
│   ├── main.py          # Главное приложение FastAPI
│   ├── models.py        # Модели базы данных
│   ├── agent.py         # Логика AI-агента
│   ├── config.py        # Конфигурация
│   ├── templates/       # HTML шаблоны
│   └── static/          # CSS/JS файлы
├── data/                # Директория для SQLite
├── Dockerfile
├── render.yaml          # Конфигурация Render
├── requirements.txt
└── README.md
```

## Промпты

Система использует 3 типа промптов:

1. **decision_agent** - Промт для принятия решений
2. **text_generator** - Генерация текста сообщений
3. **quality_checker** - Проверка качества

Все промпты можно редактировать через админ-панель.

## Переменные окружения

| Переменная | Описание | Значение по умолчанию |
|------------|----------|---------------------|
| SECRET_KEY | Секретный ключ для JWT | auto-generated |
| ADMIN_USERNAME | Логин админа | admin |
| ADMIN_PASSWORD | Пароль админа | admin123 |
| OPENAI_API_KEY | Ключ OpenAI | - |
| OPENAI_MODEL | Модель LLM | gpt-4 |
| AGENT_TEMPERATURE | Температура генерации | 0.7 |

## Лицензия

MIT
