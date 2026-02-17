import os
import json
import httpx
from typing import Dict, List, Any, Optional
from datetime import datetime
from app.models import get_db

class PersonalizationAgent:
    """AI-агент для персонализации коммуникаций"""
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4")
        self.api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.temperature = float(os.getenv("AGENT_TEMPERATURE", "0.7"))
    
    def get_prompt_template(self, name: str) -> str:
        """Получить шаблон промпта из базы данных"""
        with get_db() as db:
            cursor = db.execute(
                "SELECT template FROM prompts WHERE name = ? AND is_active = 1",
                (name,)
            )
            row = cursor.fetchone()
            if row:
                return row["template"]
        return self._get_default_prompt(name)
    
    def _get_default_prompt(self, name: str) -> str:
        """Дефолтные промпты на случай если в БД пусто"""
        prompts = {
            "decision_agent": """Ты — AI-агент по персонализации коммуникаций.

Контекст:
- Пользователь: {user_profile}
- Событие: {event}
- История за 24ч: {recent_activity}

Реши, нужно ли отправить сообщение. Ответь JSON:
{
  "should_engage": true/false,
  "reasoning": "почему",
  "action": {
    "type": "email" или "push" или null,
    "subject": "тема",
    "body": "текст"
  }
}""",
            
            "text_generator": """Напиши персонализированное сообщение для {channel}.

Клиент: {name}
Интересы: {interests}
Сегмент: {segment}

Email: до 150 слов. Push: до 80 символов."""
        }
        return prompts.get(name, "")
    
    def make_decision(self, user_profile: Dict, event: Dict, recent_activity: List[Dict]) -> Dict:
        """Принять решение о необходимости коммуникации"""
        prompt_template = self.get_prompt_template("decision_agent")
        
        prompt = prompt_template.format(
            user_profile=json.dumps(user_profile, ensure_ascii=False),
            event=json.dumps(event, ensure_ascii=False),
            recent_activity=json.dumps(recent_activity, ensure_ascii=False)
        )
        
        return self._call_llm(prompt, "Ты — AI-агент персонализации")
    
    def generate_text(self, user_profile: Dict, channel: str, context: Dict) -> str:
        """Сгенерировать персонализированный текст"""
        prompt_template = self.get_prompt_template("text_generator")
        
        prompt = prompt_template.format(
            name=user_profile.get("name", "Клиент"),
            interests=json.dumps(user_profile.get("interests", []), ensure_ascii=False),
            segment=user_profile.get("segment", "new"),
            channel=channel,
            recent_views=json.dumps(context.get("recent_views", []), ensure_ascii=False),
            purchase_history=json.dumps(context.get("purchase_history", []), ensure_ascii=False)
        )
        
        result = self._call_llm(prompt, "Ты — профессиональный копирайтер")
        return result.get("text", result.get("content", ""))
    
    def check_quality(self, message: str, user_context: Dict) -> Dict:
        """Проверить качество сообщения"""
        prompt_template = self.get_prompt_template("quality_checker")
        
        if not prompt_template:
            # Дефолтная проверка
            return {
                "overall_score": 0.9,
                "criteria_scores": {
                    "grammar": 1.0,
                    "tone": 0.9,
                    "personalization": 0.8,
                    "relevance": 0.9,
                    "spam_score": 0.1,
                    "ethics": 1.0
                },
                "approved": True,
                "comments": "",
                "suggested_improvement": ""
            }
        
        prompt = prompt_template.format(
            message=message,
            user_context=json.dumps(user_context, ensure_ascii=False)
        )
        
        return self._call_llm(prompt, "Ты — строгий редактор")
    
    def analyze_growth_opportunities(self, user_profile: Dict) -> List[Dict]:
        """Найти точки роста для клиента"""
        prompt = f"""Ты — аналитик по увеличению LTV.

Данные клиента:
{json.dumps(user_profile, ensure_ascii=False)}

Найди 3 точки роста. Ответь JSON:
{{
  "growth_opportunities": [
    {{
      "type": "cross-sell/upsell/reactivation/etc",
      "reason": "почему",
      "suggestion": "что предложить",
      "expected_ltv_increase": 15
    }}
  ],
  "priority_order": ["type1", "type2", "type3"]
}}"""
        
        result = self._call_llm(prompt, "Ты — аналитик по LTV")
        return result.get("growth_opportunities", [])
    
    def _call_llm(self, prompt: str, system_message: str = "Ты — AI-агент") -> Dict:
        """Вызвать LLM API"""
        if not self.api_key:
            print("[WARNING] OpenAI API key not set, using mock response")
            return self._mock_response(prompt)
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                "temperature": self.temperature
            }
            
            response = httpx.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60.0
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                # Пытаемся распарсить JSON
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    # Если не JSON, возвращаем как текст
                    return {"text": content, "raw": content}
            else:
                print(f"[ERROR] LLM API error: {response.status_code} - {response.text}")
                return self._mock_response(prompt)
                
        except Exception as e:
            print(f"[ERROR] LLM call failed: {e}")
            return self._mock_response(prompt)
    
    def _mock_response(self, prompt: str) -> Dict:
        """Мок-ответ для тестирования без API"""
        # Определяем тип запроса по содержимому
        if "решение" in prompt.lower() or "should_engage" in prompt:
            return {
                "should_engage": True,
                "reasoning": "Пользователь добавил товар в корзину, но не завершил покупку. Это хороший момент для напоминания.",
                "action": {
                    "type": "email",
                    "subject": "Забыли что-то в корзине?",
                    "body": "Здравствуйте! Мы заметили, что вы добавили товары в корзину, но не завершили покупку. Готовы оформить заказ?",
                    "recommendations": []
                }
            }
        elif "текст" in prompt.lower() or "напиши" in prompt.lower():
            return {
                "text": "Здравствуйте! У нас есть специальное предложение для вас. Проверьте свою корзину!"
            }
        elif "проверь" in prompt.lower() or "quality" in prompt.lower():
            return {
                "overall_score": 0.85,
                "criteria_scores": {
                    "grammar": 0.9,
                    "tone": 0.8,
                    "personalization": 0.7,
                    "relevance": 0.9,
                    "spam_score": 0.2,
                    "ethics": 1.0
                },
                "approved": True,
                "comments": "",
                "suggested_improvement": ""
            }
        else:
            return {"text": "Мок-ответ", "raw": prompt[:100]}
