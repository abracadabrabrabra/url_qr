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
├── email_utils.py
├── .gitignore
└── .env
```

## Что реализовано
- `POST /api/auth/register` - регистрация нового пользователя
- `POST /api/auth/login` - авторизация (генерация refresh и access токенов)
- `POST /api/auth/refresh` - обновление access токена
- `POST /api/auth/logout` - завершение сессии (отзыв refresh токена)
- `POST /api/auth/logout-all` - завершение всех сессий (отзыв всех refresh токенов)
- `POST /api/auth/forgot-password` - запрос сброса пароля
- `POST /api/auth/reset-password` - сброс пароля по коду
- `POST /api/auth/change-password`- защищённый эндпоинт смены пароля
- `GET /api/auth/protected` - тестовый защищённый эндпоинт
- `POST /api/shorten` - создает короткую ссылку
- `POST /api/shorten/protected` - защищённый эндпоинт создания ссылки
- `GET /api/links/{code}/stats` - статистика переходов по короткой ссылке
- `GET /api/links/{code}/analytics` - детальная аналитика по короткой ссылке за период
- `GET /api/links` - список коротких ссылок пользователя
- `GET /api/user/stats` - агрегированная статистика пользователя для dashboard
- `PATCH /api/links/{code}` - генерация нового короткого кода без потери статистики
- `DELETE /api/links/{code}` - мягкое удаление короткой ссылки пользователя
- `GET /r/{code}` делает redirect на исходный URL
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
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POSTGRES_DB=your_db
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://your_user:your_password@localhost:5432/your_db
SHORT_CODE_LENGTH=6
SHORT_CODE_ALPHABET=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789
JWT_KEY=your_jwt_secret_key_here_generate_new_one
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=noreply@yourservice.com
```

## Запуск через Docker

1. Если используется frontend, сначала соберите Vite-приложение:

```bash
cd /home/myar/PycharmProjects/url_shortener_client
npm run build
```

Nginx отдаёт готовую папку `dist` из frontend-проекта.

2. Поднимите приложение, БД и Nginx:

```bash
docker compose up --build
```

3. Основной вход через Nginx:

```text
http://localhost
```

Swagger будет доступен по адресу:

```text
http://localhost/docs
```

Backend напрямую оставлен для отладки:

```text
http://localhost:8001/docs
```

## Nginx

В проект добавлен Nginx как единая точка входа для frontend и backend.

Что это дает:

- frontend и backend открываются на одном origin `http://localhost`, поэтому меньше проблем с CORS, cookies и токенами
- Vite `dist` отдается как статические файлы без запуска dev-сервера
- `/api/...` и `/r/{code}` проксируются во внутренний контейнер FastAPI
- короткие ссылки не конфликтуют с frontend routes вроде `/login`, `/dashboard`, `/links/...`
- в production Nginx можно использовать для TLS/HTTPS, gzip/brotli, кеширования статики и reverse proxy

Схема:

```text
Browser
  |
Nginx :80
  |-- /, /login, /dashboard, /links/... -> frontend dist
  |-- /api/...                          -> FastAPI app:8000
  |-- /docs                             -> FastAPI app:8000
  |-- /openapi.json                     -> FastAPI app:8000
  |-- /r/{code}                         -> FastAPI redirect
```

Короткие ссылки вынесены под префикс `/r`, чтобы не конфликтовать с frontend routes:

```text
http://localhost/r/FnhXPE
```

Конфигурация Nginx находится в `nginx.conf`.

Проверка после запуска:

```bash
curl http://localhost/api/health
curl -I http://localhost/r/FnhXPE
```

Frontend должен обращаться к API относительными путями:

```text
/api/auth/login
/api/user/links
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

### Запрос на сброс пароля с отправкой кода на email

```cmd
curl -X POST "http://localhost:8000/api/auth/forgot-password"  ^
 -H "Content-Type: application/json" ^
 -d "{\"email\": \"example@mail.com\"}"
```

Пример ответа:

```json
{"msg":"If your email is registered, you will receive a reset code"}
```

### Смена пароля по коду с email

```cmd
curl -X POST "http://localhost:8000/api/auth/reset-password" ^
 -H "Content-Type: application/json" ^
 -d "{\"email\": \"example@mail.com\", \"code\": \"123456\", \"new_password\": \"newpass\"}"
```

Успешный сценарий:

```json
{"msg":"Password has been reset successfully"}
```

Ответ при невалидном коде:

```json
{"detail":"Invalid or expired reset code"}
```

### Защищённый эндроинт смены пароля

```cmd
curl -X POST "http://localhost:8000/api/auth/change-password" -H "Content-Type: application/json" ^
 -H "Authorization: Bearer <access_token>" ^
 -d "{\"old_password\": \"oldpass\", \"new_password\": \"newpass\"}"
```

Успешный сценарий:

```json
{"msg":"Password has been reset successfully"}
```

Ответ при невалидном access-токене:

```json
{"detail":"Not authenticated"}
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
  "short_url": "http://localhost:8000/r/Ab3dE1"
}
```

Защищенная версия

```cmd
curl -X POST "http://localhost:8000/api/shorten/protected" ^
 -H "Content-Type: application/json" -H "Authorization: Bearer <access_token>" ^
 -d "{\"original_url\": \"https://example.com/very/long/url\"}"
```

Пример ответа:

```json
{
  "original_url":"https://example.com/very/long/url",
  "short_code":"nXiI0r",
  "short_url":"http://localhost:8000/r/nXiI0r",
  "user_id":1
}

```
Валидация `original_url`:
- URL должен быть валидным и содержать схему и домен
- разрешены только схемы `http` и `https`
- домен обязателен и должен быть полноценным, например `example.com`; значения вроде `https://123` или `https://test` не принимаются

Примеры ошибок:

```json
{"detail":"URL must be valid and include scheme and host"}
```

```json
{"detail":"Only http and https URLs are allowed"}
```

```json
{"detail":"URL host must be a valid domain"}
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
    "short_url":"http://localhost:8000/r/6GjDtf",
    "user_id":1,
    "clicks_count":1,
    "created_at":"2026-05-28 08:36:47.579602",
    "is_active":true
  }
]
```

### Обновление короткого кода ссылки

Эндпоинт генерирует новый короткий код для существующей ссылки без потери статистики. Пользователь не передает свой вариант `short_key`: новый код создается сервером тем же алгоритмом, что и при создании ссылки.

`original_url`, `clicks_count`, `created_at` и история переходов из `visits` сохраняются.

Пример запроса

```cmd
curl -X PATCH "http://localhost:8000/api/links/nXiI0r" ^
 -H "Authorization: Bearer <access_token>"
```

Пример ответа:

```json
{
  "old_short_key":"nXiI0r",
  "short_key":"Ab3dE1",
  "short_url":"http://localhost:8000/r/Ab3dE1",
  "original_url":"https://example.com",
  "clicks_count":342,
  "created_at":"2026-05-20T14:29:03",
  "is_active":true
}
```

### Удаление короткой ссылки

Эндпоинт выполняет мягкое удаление: ссылка остается в базе данных, но получает `is_active=false` и `deleted_at`, поэтому скрывается из обычного списка `/api/user/links` и перестает работать для редиректа.

Пример запроса

```cmd
curl -X DELETE "http://localhost:8000/api/links/nXiI0r" -H "Authorization: Bearer <access_token>"
```

Пример ответа:

```json
{
  "msg":"Link deleted successfully",
  "short_key":"nXiI0r",
  "is_active":false,
  "deleted_at":"2026-06-05T12:30:00"
}
```

### Агрегированная статистика пользователя

Пример запроса

```cmd
curl -X GET "http://localhost:8000/api/user/stats" -H "Authorization: Bearer <access_token>"
```

Пример ответа:

```json
{
  "total_links":24,
  "total_clicks":1456,
  "clicks_today":23,
  "clicks_this_month":312
}
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

### Детальная аналитика по короткой ссылке

Возвращает аналитику за выбранный период. Параметры `date_from` и `date_to` передаются в формате `YYYY-MM-DD`.

Уникальный клик считается по паре `ip_address + user_agent`.

Поле `comparison` показывает изменение в процентах относительно предыдущего периода такой же длины. Например, для периода `2026-05-12` - `2026-05-18` сравнение будет с `2026-05-05` - `2026-05-11`.

Пример запроса

```cmd
curl -X GET "http://localhost:8000/api/links/nXiI0r/analytics?date_from=2026-05-12&date_to=2026-05-18" -H "Authorization: Bearer <access_token>"
```

Пример ответа:

```json
{
  "short_key":"nXiI0r",
  "short_url":"http://localhost:8000/r/nXiI0r",
  "original_url":"https://example.com",
  "total_clicks":342,
  "unique_clicks":287,
  "average_per_day":48,
  "last_click_at":"2026-05-18T14:32:00",
  "created_at":"2026-05-20T14:29:03",
  "is_active":true,
  "daily_clicks":[
    {
      "date":"2026-05-12",
      "clicks":27
    },
    {
      "date":"2026-05-13",
      "clicks":42
    }
  ],
  "comparison":{
    "total_clicks_percent":18,
    "unique_clicks_percent":15,
    "average_per_day_percent":12
  }
}
```


### Редирект по короткому коду

```bash
curl -i "http://localhost:8000/r/Ab3dE1"
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
curl -i "http://localhost:8000/r/unknown"
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

QR-код содержит короткую ссылку вида `/r/{code}`, а не исходный `original_url`.
Поэтому сканирование QR проходит через редирект сервиса и учитывается в общей статистике переходов.

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

## Нагрузочное тестирование редиректа

Для проверки частых переходов по короткой ссылке использовался `hey`.

Команда для spike-теста через Nginx:

```bash
hey -disable-redirects -n 2000 -c 2000 http://127.0.0.1/r/FnhXPE
```

Параметры:

- `-n 2000` - всего 2000 запросов
- `-c 2000` - до 2000 одновременных запросов
- `-disable-redirects` - не переходить на внешний сайт после получения `307`

Зафиксированный локальный результат после добавления Nginx и запуска FastAPI с 4 workers:

```text
Status code distribution:
  [307] 2000 responses

Requests/sec: 1187.7159
Average:      0.9959 sec
p50:          0.9903 sec
p95:          1.5648 sec
p99:          1.6398 sec
```

Итог: локальный spike на 2000 одновременных редиректов прошёл без ошибок. Тест выполнялся локально, поэтому результат зависит от машины, Docker, PostgreSQL и текущей нагрузки системы.

Как читать результат:

- `Status code distribution: [307] 2000 responses` означает, что все 2000 запросов получили корректный redirect
- отсутствие `Error distribution` означает, что во время теста не было `EOF`, timeout или отказов соединения
- `Requests/sec` показывает пропускную способность на этой машине, но это не универсальная production-цифра
- `p95` и `p99` важнее среднего времени, потому что показывают задержку для самых медленных запросов
- если `/api/health` работает сильно быстрее, чем `/r/{code}`, значит узкое место находится не в Nginx, а в логике редиректа: запрос к БД, запись визита, пул соединений или PostgreSQL

## Основные файлы

- `main.py` создает приложение FastAPI и подключает роутеры
- `config.py` читает настройки из `.env`
- `database.py` настраивает async engine и сессию SQLAlchemy
- `models.py` описывает ORM-модели `Link` и `User` под исходные таблицы `links` и `users`
- `docker-compose.yml` поднимает приложение и PostgreSQL в контейнерах
- `Dockerfile` собирает контейнер приложения
- `nginx.conf` настраивает маршрутизацию frontend/API/редиректов через Nginx
- `services.py` содержит бизнес-логику создания короткой ссылки
- `auth_services.py` содержит логику работы с JWT токенами (создание, отзыв, хэширование и т.д.)
- `routers/links.py` содержит HTTP-эндпоинты
- `routers/auth.py` содержит HTTP-эндпоинты авторизации
- `qr_generator.py` содержит функции для генерации qr-кодов(простых, с кастомными цветами) и для наложения логотипа
- `static_data/logo.png` стандартный логотип, накладываемый на qr-коды
