# Instagram Meta Webhook

FastAPI webhook для обработки комментариев Instagram. Сервис проверяет подпись Meta, использует SQLite для дедупликации и при включённом автоответе обращается к Instagram Graph API.

## Настройка и запуск

```bash
cp .env.example .env
nano .env
chmod 600 .env
```

Сгенерируйте `META_VERIFY_TOKEN` командой `openssl rand -hex 32`. Укажите в `.env` verify token, Instagram access token, Meta App Secret и Instagram User ID. Если автоответ включён, задайте непустое `META_AUTO_REPLY_MESSAGE`.

```bash
docker compose build
docker compose up -d
docker compose ps
```

Проверка health endpoint:

```bash
curl http://127.0.0.1:8002/health
```

Ожидаемый ответ: `{"status":"ok"}`.

Проверка Meta challenge:

```bash
curl -i \
  "http://127.0.0.1:8002/meta/instagram/webhook?hub.mode=subscribe&hub.verify_token=<VERIFY_TOKEN>&hub.challenge=123456"
```

Ожидается HTTP 200 и body `123456`.

## Nginx

Добавьте в HTTPS server block:

```nginx
location = /meta/instagram/webhook {
    access_log off;

    proxy_pass http://127.0.0.1:8002;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_connect_timeout 5s;
    proxy_read_timeout 15s;
}
```

Для health endpoint при необходимости:

```nginx
location = /health {
    proxy_pass http://127.0.0.1:8002;
}
```

## Meta Dashboard и подписка

Callback URL: `https://<DOMAIN>/meta/instagram/webhook`. Verify Token: значение `META_VERIFY_TOKEN`. Подпишитесь на поле `comments`.

После заполнения `.env` выполните:

```bash
set -a
source .env
set +a

curl -X POST \
  "https://graph.instagram.com/v26.0/28201449176138547/subscribed_apps" \
  --data-urlencode "subscribed_fields=comments" \
  --data-urlencode "access_token=$META_ACCESS_TOKEN"
```

Проверка подписки:

```bash
curl \
  "https://graph.instagram.com/v26.0/28201449176138547/subscribed_apps?access_token=$META_ACCESS_TOKEN"
```
