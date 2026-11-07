# VPS за 10 минут: постоянный адрес для показа

Подходит, когда нужно «кинуть работодателю ссылку»: сервер работает круглосуточно,
адрес не меняется, засыпания нет.

Нужен любой VPS с Ubuntu 22.04/24.04 (1 ядро, 1 ГБ RAM достаточно).
Ориентиры: Timeweb Cloud, Aeza, Beget — примерно 200–350 ₽/мес, оплата картой РФ.
Домен покупать не обязательно: вместо него работает `sslip.io`.

---

## 1. Купить VPS и узнать IP

В панели хостинга создайте сервер: Ubuntu 24.04, 1 vCPU, 1 ГБ, публичный IPv4.
Запишите IP, например `203.0.113.10`.

## 2. Подключиться

Windows: откройте PowerShell и выполните (пароль придёт в панели или на почту):

```powershell
ssh root@203.0.113.10
```

## 3. Поставить Docker

```bash
curl -fsSL https://get.docker.com | sh
```

## 4. Загрузить проект

**Вариант А — с вашего компьютера** (в новом окне PowerShell, не в SSH):

```powershell
scp -r "C:\Users\meow\Desktop\мессенджер" root@203.0.113.10:/opt/omega
```

**Вариант Б — с GitHub** (если репозиторий уже есть):

```bash
apt install -y git
git clone https://github.com/ВАШ_ЛОГИН/omega-messenger.git /opt/omega
```

## 5. Настроить домен и запустить

В SSH-сессии:

```bash
cd /opt/omega
mkdir -p data
cp .env.example .env
nano .env          # впишите DOMAIN=203.0.113.10.sslip.io и сохраните (Ctrl+O, Enter, Ctrl+X)
docker compose up -d --build
```

Первый запуск занимает 2–4 минуты (сборка образа).

## 6. Проверить

```bash
docker compose logs -f caddy     # ждём "certificate obtained successfully", Ctrl+C
curl https://203.0.113.10.sslip.io/
```

Должно вернуться `Omega E2E server is running. Online: 0, known: 0`.

Если сертификат не выдаётся — почти всегда закрыт порт 80. Проверьте firewall
у хостинга (Security Group) и внутри: `ufw allow 80/tcp && ufw allow 443/tcp`.

## 7. Адрес для клиента

```
wss://203.0.113.10.sslip.io/ws
```

Его вводят в окне входа (или он уже вписан в архив, собранный скриптом
`deploy\make_client_package.py`).

## 8. Обслуживание

```bash
docker compose ps                 # статус
docker compose logs -f omega      # логи сервера (кто вошёл, ошибки)
docker compose restart omega      # перезапуск
```

Данные: `./data/keyring.json` — закреплённые ключи. Делайте копию:

```bash
cp data/keyring.json ~/keyring-$(date +%F).json
```

Перенос на другой сервер = скопировать проект вместе с `data/`.

---

## Сколько это стоит и что выбрать

| Вариант | Цена | Спит? | Адрес | Кому подходит |
|---|---|---|---|---|
| **VPS + Docker (этот файл)** | 200–350 ₽/мес | нет | постоянный | показ работодателю, «поставил и забыл» |
| Render Free | 0 | да, через 15 мин | постоянный | быстрый бесплатный тест |
| Oracle Always Free | 0 | нет | постоянный | если готовы повозиться с регистрацией |
| Свой ПК + Cloudflare Tunnel | 0 | нет, пока ПК включён | меняется при перезапуске | локальные тесты |

## Если Render

1. Репозиторий на GitHub → Render → **New → Web Service** → Python 3.
2. Build: `pip install -r requirements.txt`, Start: `python server.py`, Plan: Free.
3. Адрес будет `https://omega-xxxx.onrender.com`, клиенту — `wss://omega-xxxx.onrender.com/ws`.
4. Перед показом откройте адрес в браузере за пару минут — сервис проснётся,
   дальше он живёт, пока идёт подключение. Для страховки можно повесить
   бесплатный пингер (cron-job.org) раз в 10 минут.
5. Помните: на бесплатном плане `keyring.json` сбрасывается при перезапуске —
   контакты заново подтвердят отпечатки.
