## Структура проекта

```text
.
├── config.py
├── database.py
├── docker-compose.yml
├── Dockerfile
├── link_shortener.sql
├── main.py
├── models.py
├── requirements.txt
├── README.md
├── routers
│   ├── __init__.py
│   └── links.py
├── services.py
└── .env
```

## Что реализовано

- `POST /api/shorten` создает короткую ссылку
- `GET /{code}` делает redirect на исходный URL
- `GET /api/health` проверяет доступность сервиса
- хранение ссылок в PostgreSQL
- генерация уникального `short_code` длиной 6 символов


## Настройка окружения

1. Создайте в корне проекта файл `.env`:

```env
APP_NAME=URL Shortener API
APP_HOST=0.0.0.0
APP_PORT=8000
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=url_shortener
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/url_shortener
SHORT_CODE_LENGTH=6
SHORT_CODE_ALPHABET=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789
```

## Запуск через Docker

1. Поднимите приложение и БД:

```bash
docker compose up --build
```

2. Swagger будет доступен по адресу:

```text
http://localhost:8000/docs
```

## Локальный запуск без Docker

Если Docker не нужен, можно запускать приложение отдельно, а БД поднять любым удобным способом.

1. Создайте и активируйте виртуальное окружение:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Установите зависимости:

```bash
pip install -r requirements.txt
```

3. Поднимите PostgreSQL и выполните ваш SQL-скрипт.

4. Запустите сервер:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Swagger будет доступен по адресу:

```text
http://localhost:8000/docs
```

## Примеры запросов

### Создание короткой ссылки

```bash
curl -X POST "http://localhost:8000/api/shorten" \
  -H "Content-Type: application/json" \
  -d '{
    "original_url": "https://example.com/very/long/url"
  }'
```

```cmd
curl -X POST "http://localhost:8000/api/shorten" -H "Content-Type: application/json" -d "{\"original_url\": \"https://example.com/very/long/url\"}"
```

Пример ответа:

```json
{
  "original_url": "https://example.com/very/long/url",
  "short_code": "Ab3dE1",
  "short_url": "http://localhost:8000/Ab3dE1"
}
```

### Редирект по короткому коду

```bash
curl -i "http://localhost:8000/Ab3dE1"
```

Ожидаемый ответ:

```text
HTTP/1.1 307 Temporary Redirect
date: Tue, 28 Apr 2026 16:07:32 GMT
server: uvicorn
content-length: 0
location: https://example.com/very/long/url

```

### Ошибка при несуществующем или неактивном коде

```bash
curl -i "http://localhost:8000/unknown"
```

Ожидаемый ответ:

```text
HTTP/1.1 404 Not Found
date: Tue, 28 Apr 2026 16:08:38 GMT
server: uvicorn
content-length: 33
content-type: application/json

{"detail":"Short code not found"}
```

### Проверка доступности сервиса

```bash
curl "http://localhost:8000/api/health"
```

Ожидаемый ответ:

```json
{
  "status": "ok"
}
```

### Генерация простого qr по короткому коду

```cmd
curl "http://localhost:8000/api/qr/example_correct_shortcode" --output output_filepath --fail
```

Ожидаемый ответ:

```text
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   736    0   736    0     0   9156      0 --:--:-- --:--:-- --:--:--  9200

```

### Ошибка при несуществующем или неактивном коде

```cmd
curl "http://localhost:8000/api/qr/example_incorrect_shortcode" --output output_filepath --fail
```

Ожидаемый ответ:

```text
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
curl: (22) The requested URL returned error: 404
```

## Как работает генерация `short_code`

В `services.py` код генерируется случайно:

- длина кода задается через `SHORT_CODE_LENGTH`
- допустимые символы задаются через `SHORT_CODE_ALPHABET`
- для выбора символов используется модуль `secrets`

## Как решается проблема коллизий

Коллизия означает, что сгенерированный код уже есть в поле `links.short_key`.

Решение:

1. Генерируем новый код.
2. Проверяем его через запрос в БД.
3. Если код уже существует, генерируем следующий.
4. Если код свободен, сохраняем запись.

В проекте для этого используется цикл с ограничением по числу попыток. Дополнительно на `commit` обрабатывается `IntegrityError`, чтобы закрыть гонку между параллельными запросами.

## Генерация qr-кодов

Для генерации qr-кодов используется библиотека segno. Её преимущества:

- высокая производительность
- минимальные зависимости - не требует дополнительных библиотек
- встроенная цветовая кастомизация

## Основные файлы

- `main.py` создает приложение FastAPI и подключает роутеры
- `config.py` читает настройки из `.env`
- `database.py` настраивает async engine и сессию SQLAlchemy
- `models.py` описывает ORM-модели `Link` и `User` под исходные таблицы `links` и `users`
- `docker-compose.yml` поднимает приложение и PostgreSQL в контейнерах
- `Dockerfile` собирает контейнер приложения
- `services.py` содержит бизнес-логику создания короткой ссылки
- `routers/links.py` содержит HTTP-эндпоинты
- `qr_generator.py` содержит модульные функции для генерации qr-кодов(простых, с логотипом, с кастомными цветами)
