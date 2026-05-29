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
├── qr_generator.py
├── requirements.txt
├── README.md
├── routers
│   ├── __init__.py
│   ├── auth.py
│   └── links.py
├── static_data
│   ├── bauman_logo.png
│   └── logo.png
├── services.py
├── auth_services.py
├── .gitignore
└── .env
```

## Что реализовано
- `POST /api/auth/register` - регистрация нового пользователя
- `POST /api/auth/login` - авторизация (генерация refresh и access токенов)
- `POST /api/auth/refresh` - обновление acess токена
- `POST /api/auth/logout` - завершение сессии (отзыв refresh токена)
- `POST /api/auth/logout-all` - завершение всех сессий (отзыв всех refresh токенов)
- `GET /api/auth/protected` - тестовый защищённый эндпоинт
- `POST /api/shorten` - создает короткую ссылку
- `POST /api/shorten/protected` - защищённый эндпоинт создания ссылки
- `GET /api/links/{code}/stats` - статистика переходов по короткой ссылке
- `GET /api/links` - список коротких ссылок пользователя
- `GET /{code}` делает redirect на исходный URL
- `GET /api/qr/{code}` - генерация черно-белого qr-кода для существующей короткой ссылки
- `POST /api/qr/{code}/custom` - генерация кастомного qr-кода для существующей короткой ссылки
- `GET /api/health` проверяет доступность сервиса
- хранение ссылок в PostgreSQL
- генерация уникального `short_code` длиной 6 символов
- кастомизация qr-кодов (загрузка пользовательских логотипов и цветов)

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

### Регистрация нового пользователя

```cmd
curl -X POST "http://localhost:8000/api/auth/register" ^
 -H "Content-Type: application/json" ^
 -d "{\"email\": \"example@mail.com\", \"password\": \"123\"}"
```

Пример ответа:

```json
{"msg":"User created successfully","user_id":1,"email":"example@mail.com"}
```

### Авторизация

```cmd
curl -X POST "http://localhost:8000/api/auth/login" ^
 -H "Content-Type: application/x-www-form-urlencoded" ^
 -d "username=example@mail.com&password=123"
```

Пример ответа:

```json
{"access_token":"<access_token>","refresh_token":"<refresh_token>","token_type":"bearer"}
```

### Обновление access токена

```cmd
curl -X POST "http://localhost:8000/api/auth/refresh" ^
 -H "Content-Type: application/json" ^
 -d "{\"refresh_token\": \"<refresh_token>\"}"
```

Пример ответа:

```json
{"access_token":"<access_token>","refresh_token":"<refresh_token>","token_type":"bearer"}
```

Ошибка при невалидном refresh токене:

```json
{"detail":"Invalid or expired refresh token"}
```


### Завершение сессии

```cmd
curl -X POST "http://localhost:8000/api/auth/logout" ^
 -H "Content-Type: application/json" ^
 -d "{\"refresh_token\": \"<refresh_token>\"}"
```

Пример ответа:

```json
{"msg":"Successfully logged out"}
```

### Завершение всех сессий

```cmd
curl -X POST "http://localhost:8000/api/auth/logout-all" -H "Authorization: Bearer <access_token>"
```

Пример ответа:

```json
{"msg":"Successfully logged out from all 2 devices"}
```

### Создание короткой ссылки

Публичная версия

```bash
curl -X POST "http://localhost:8000/api/shorten" \
  -H "Content-Type: application/json" \
  -d '{
    "original_url": "https://example.com/very/long/url"
  }'
```

```cmd
curl -X POST "http://localhost:8000/api/shorten" ^
 -H "Content-Type: application/json" ^
 -d "{\"original_url\": \"https://example.com/very/long/url\"}"
```

Пример ответа:

```json
{
  "original_url": "https://example.com/very/long/url",
  "short_code": "Ab3dE1",
  "short_url": "http://localhost:8000/Ab3dE1"
}
```

Защищенная версия

```cmd
curl -X POST "http://localhost:8000/api/shorten/protected" ^
 -H "Content-Type: application/json" -H "Authorization: Bearer <access_token>" ^
 -d "{\"original_url\": \"example_url\"}"
```

Пример ответа:

```json
{
  "original_url":"example_url",
  "short_code":"nXiI0r",
  "short_url":"http://localhost:8000/nXiI0r",
  "user_id":1
}

```
Ошибка при невалидном access токене:

```json
{"detail":"Invalid authentication credentials"}
```

### Тестовый защищенный эндпоинт

Пример запроса

```cmd
curl -X GET "http://localhost:8000/api/auth/protected" -H "Authorization: Bearer <access_token>"
```

Пример ответа:

```json
{
  "message":"Hello example@mail.com, you have access to protected data!",
  "user_id":1,"email":"example@mail.com",
  "is_active":true,
  "created_at":"2026-05-20 15:00:26.318913"
}
```

### Список коротких ссылок пользователя

Пример запроса

```cmd
curl -X GET "http://localhost:8000/api/user/links" -H "Authorization: Bearer <access_token>"
```

Пример ответа:

```json
[
  {
    "original_url":"https://very_long_url",
    "short_code":"6GjDtf",
    "short_url":"http://localhost:8000/6GjDtf",
    "user_id":1,
    "clicks_count":1,
    "created_at":"2026-05-28 08:36:47.579602",
    "is_active":true
  }
]
```

### Статистика по короткой ссылке

Пример запроса

```cmd
curl -X GET "http://localhost:8000/api/links/short_code/stats" -H "Authorization: Bearer <access_token>"
```

Пример ответа:

```json
{
  "short_key":"nXiI0r",
  "clicks_count":2,
  "created_at":"2026-05-20 14:29:03.033408",
  "is_active":true
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

### Генерация черно-белого qr по короткому коду

```cmd
curl -X POST "http://localhost:8000/api/qr/example_short_code/custom" --output filepath --fail
```

```cmd
curl "http://localhost:8000/api/qr/example_short_code" --output filepath --fail
```

### Генерация цветного qr по короткому коду

```cmd
curl -X POST "http://localhost:8000/api/qr/example_short_code/custom" ^
-F "dark_color=#FF0000" ^
-F "light_color=#FFFFFF" ^
--output qr_default.png --fail
```

### Генерация черно-белого qr-кода со стандартным логотипом

```cmd
curl -X POST "http://localhost:8000/api/qr/example_short_code/custom" ^
-F "use_default_logo=true" ^
--output qr_default.png --fail
```

### Генерация черно-белого qr-кода с кастомным логотипом

```cmd
curl -X POST "http://localhost:8000/api/qr/example_short_code/custom" ^
-F "logo_file=@C:\logo_path.png" ^
--output qr_default.png --fail
```

### Генерация цветного qr-кода со стандартным логотипом

```cmd
curl -X POST "http://localhost:8000/api/qr/example_short_code/custom" ^
-F "use_default_logo=true" ^
-F "dark_color=#FF0000" ^
-F "light_color=#FFFFFF" ^
-F "scale=15" ^
--output qr_default.png --fail
```

### Генерация цветного qr-кода с кастомным логотипом

```cmd
curl -X POST "http://localhost:8000/api/qr/example_short_code/custom" ^
-F "logo_file=@C:\logo_path.png" ^
-F "dark_color=#FF0000" ^
-F "light_color=#FFFFFF" ^
-F "scale=15" ^
--output qr_default.png --fail
```

Ожидаемый ответ для всех запросов на генерацию qr-кодов:

```text
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   818    0   754  100    64   9299    789 --:--:-- --:--:-- --:--:-- 10098

```

### Ошибка при несуществующем или неактивном коде для всех запросов на генерацию qr-кодов

```cmd
curl -X POST "http://localhost:8000/api/qr/example_invalid_short_code/custom" --output qr_default.png --fail
```

Ответ:

```text
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
  0     0    0     0    0     0      0      0 --:--:-- --:--:-- --:--:--     0
curl: (22) The requested URL returned error: 404
```

### Ошибка при некорректном формате цветов

```cmd
curl -X POST "http://localhost:8000/api/qr/example_short_code/custom" ^
-F "dark_color=FF0000A123fs" ^
-F "light_color=#*90" ^
--output qr_default.png --fail
```

Ответ:

```text
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   281    0     0  100   281      0   6585 --:--:-- --:--:-- --:--:--  6690
curl: (22) The requested URL returned error: 400
```

### Ошибка при некорректном формате файла с логотипом(допустимы: .jpg, .jpeg, .png)

```cmd
curl -X POST "http://localhost:8000/api/qr/GAS7Li/custom" ^
-F "logo_file=@C:\invalid_file.sql" ^
--output qr_default.png --fail
```

Ответ:

```text
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100   281    0     0  100   281      0   6585 --:--:-- --:--:-- --:--:--  6690
curl: (22) The requested URL returned error: 400
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
- `auth_services.py` содержит логику работы с JWT токенами (создание, отзыв, хэширование и т.д.)
- `routers/links.py` содержит HTTP-эндпоинты
- `routers/auth.py` содержит HTTP-эндпоинты авторизации
- `qr_generator.py` содержит функции для генерации qr-кодов(простых, с кастомными цветами) и для наложения логотипа
- `static_data/logo.png` стандартный логотип, накладываемый на qr-коды
