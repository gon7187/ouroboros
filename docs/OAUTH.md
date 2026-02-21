# OAuth Authorization Module

Модуль для авторизации через OAuth 2.0 в OpenAI.

## Что это даёт

Возможность получать OAuth токены для доступа к OpenAI API без использования API ключей (`sk-proj-...`).

## Как работает

**OAuth 2.0 Authorization Code Flow с PKCE:**

1. Генерируется авторизационная ссылка
2. Пользователь переходит по ссылке и авторизует приложение
3. OpenAI перенаправляет на redirect URI с кодом авторизации
4. Код обменивается на access token и refresh token
5. Access token используется для API запросов
6. Refresh token используется для обновления access token

## Структура

```
ouroboros/auth/
├── __init__.py      # Модуль auth
└── oauth.py         # OAuth 2.0 клиент

scripts/
└── oauth_auth.py    # CLI инструмент для интерактивной авторизации

tests/
└── test_oauth.py    # Тесты
```

## Использование

### 1. Через CLI (простой способ)

```bash
python scripts/oauth_auth.py
```

Скрипт:
1. Спросит client ID (или использует из clawd bot конфига)
2. Сгенерирует авторизационную ссылку
3. Попросит вставить redirect URL после авторизации
4. Получит access token
5. Предложит сохранить токен в файл

### 2. Программно

```python
from ouroboros.auth.oauth import OpenAIClient

# Инициализация клиента
client = OpenAIClient(
    client_id="app_xxxxxxxxxxxxxxxx",
    redirect_uri="http://localhost:3000/callback",
)

# Шаг 1: Получить авторизационную ссылку
auth_url = client.get_authorization_url()
print(f"Visit: {auth_url}")

# Шаг 2: Пользователь авторизуется, получает redirect URL
redirect_url = input("Paste redirect URL: ")

# Шаг 3: Получить access token
access_token = client.get_access_token(redirect_url)
print(f"Access token: {access_token}")

# Шаг 4 (опционально): Проверить JWT
payload = client.decode_jwt(access_token)
print(f"Token payload: {payload}")

# Шаг 5 (опционально): Проверить истечение
if client.is_token_expired(access_token):
    print("Token expired!")
```

### 3. Обновление токена через refresh token

```python
from ouroboros.auth.oauth import OpenAIClient

client = OpenAIClient(client_id="app_xxxxxxxxxxxxxxxx")

# Использовать refresh token для получения нового access token
tokens = client.refresh_tokens(refresh_token="rt_...")
new_access_token = tokens.access_token
```

## Конфигурация

### OpenAI Client ID

OpenAI OAuth client ID можно получить из:

1. **Clawd bot конфиг** (если есть):
   ```bash
   cat ~/.openclaw/openclaw.json | grep OPENAI_OAUTH_CLIENT_ID
   ```

2. **OpenAI Developer Portal** (создать своё приложение):
   - Перейти на https://platform.openai.com/apps
   - Создать OAuth приложение
   - Получить Client ID

### Redirect URI

Default: `http://localhost:3000/callback`

Для изменения:
```python
client = OpenAIClient(
    client_id="app_xxxxxxxxxxxxxxxx",
    redirect_uri="https://your-app.com/callback",  # Ваш redirect URI
)
```

## Токены

### Access Token

- Тип: JWT
- Используется для авторизации в API
- Пример заголовка запроса:
  ```
  Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
  ```

### Refresh Token

- Используется для получения нового access token без повторной авторизации
- Формат: `rt_...`

### Хранение токенов

Рекомендуемое место: `~/.openclaw/agents/main/agent/auth.json`

Формат:
```json
{
  "openai-oauth": {
    "type": "oauth",
    "access": "eyJhbGciOiJSUzI1NiIs...",
    "refresh": "rt_xxxxxx...",
    "expires": 1772429642842
  }
}
```

## OAuth Scopes

Default scopes:
- `openid` — OpenID Connect
- `profile` — Профиль пользователя
- `email` — Email пользователя
- `offline_access` — Refresh token

Для изменения:
```python
client = OpenAIClient(
    client_id="app_xxxxxxxxxxxxxxxx",
    scopes=["openid", "profile", "email", "offline_access", "api.read"],
)
```

## Безопасность

### PKCE (Proof Key for Code Exchange)

Модуль использует PKCE — стандарт для public clients (без client secret):

- Генерируется случайный `code_verifier`
- Вычисляется `code_challenge` = SHA256(verifier)
- Challenge отправляется в авторизационном запросе
- Verifier используется для обмена кода на токен

Это защищает от перехвата authorization code.

### State Parameter

Защита от CSRF атаки:
- Генерируется случайный state
- Отправляется в авторизационном запросе
- Проверяется в redirect URL

### Рекомендации

1. **Не коммитить токены в git**
2. **Использовать environment variables для client secret** (если есть)
3. **Проверять истечение токена перед каждым запросом**
4. **Использовать HTTPS для redirect URI** в production

## Тесты

Запуск тестов:
```bash
pytest tests/test_oauth.py -v
```

Все тесты проверяют:
- Генерацию PKCE пар
- Создание авторизационных URL
- Парсинг redirect URL
- Декодирование JWT
- Проверку истечения токена
- Обработку ошибок

## Ошибки

### PKCEError

```
PKCE verifier not generated. Call get_authorization_url() first.
```

**Причина:** Попытка обменять код без генерации verifier.

**Решение:** Сначала вызвать `client.get_authorization_url()`.

### TokenExchangeError

```
Token exchange failed: 400 - {"error": "invalid_code"}
```

**Причина:** Код авторизации недействителен или истёк.

**Решение:** Повторить процесс авторизации.

### RefreshTokenError

```
Token refresh failed: 401 - {"error": "invalid_refresh_token"}
```

**Причина:** Refresh token недействителен.

**Решение:** Повторить процесс авторизации.

## Интеграция с LLM провайдерами

OAuth токены можно использовать для доступа к:

1. **OpenAI API** (`api.openai.com/v1`)
2. **ChatGPT Backend API** (`chatgpt.com/backend-api`)

Пример с OpenAI API:
```python
import httpx

access_token = "eyJhbGciOiJSUzI1NiIs..."

response = httpx.post(
    "https://api.openai.com/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {access_token}",
    },
    json={
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "Hello"}],
    },
)
```

## Roadmap

- [ ] Добавить поддержку других OAuth провайдеров (Google, GitHub)
- [ ] Автоматическое обновление токенов при истечении
- [ ] Интеграция с LLM провайдерами в `llm.py`
- [ ] Кэширование токенов для уменьшения запросов

## Проблемы и ограничения

### Cloudflare Protection

ChatGPT backend API (`chatgpt.com/backend-api`) защищён Cloudflare. OAuth токен не работает напрямую через HTTP requests — нужен браузер или обход Cloudflare.

**Решение:** Использовать OpenAI API (`api.openai.com/v1`) или браузерную автоматизацию.

### Token Expiration

Access tokens истекают через определённое время (обычно 1 час). Нужно использовать refresh token или повторять авторизацию.

## Полезные ссылки

- [OpenAI OAuth Documentation](https://platform.openai.com/docs/guides/production-best-practices/authentication)
- [OAuth 2.0 RFC 6749](https://tools.ietf.org/html/rfc6749)
- [PKCE RFC 7636](https://tools.ietf.org/html/rfc7636)
