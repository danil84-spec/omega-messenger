# Где разместить сервер OMEGA

Серверу нужен только Python 3.10+ и открытый порт. Состояние — один файл
`keyring.json` (закреплённые публичные ключи) и офлайн-очередь в памяти.
TLS можно не настраивать на самом сервере: у большинства хостингов HTTPS/WSS
терминируется на их прокси.

Клиент всегда подключается по адресу `wss://<домен>/ws` (или `ws://IP:8080/ws`,
если сервер без TLS в локальной сети).

| Вариант | Цена | Время | Плюсы | Минусы |
|---|---|---|---|---|
| A. Render | 0 ₽ | 10 мин | Ничего не администрировать | Засыпает через 15 мин, keyring стирается при рестарте |
| B. Oracle Cloud Always Free | 0 ₽ | 40 мин | Постоянная VM, полный контроль | Нужна карта для верификации, своя возня с TLS |
| C. Свой ПК + Cloudflare Tunnel | 0 ₽ | 5 мин | Работает сегодня, данные у вас | ПК включён, адрес меняется |
| D. Дешёвый VPS | ~200–400 ₽/мес | 30 мин | Предсказуемо, постоянный домен | Платно |

## Что выбрать для показа работодателю

Нужен адрес, который откроется в любой момент и не поменяется, — поэтому:

1. **VPS + Docker** — [vps-quickstart.md](vps-quickstart.md). 10 минут, 200–350 ₽/мес,
   домен не нужен (работает `sslip.io`), HTTPS настраивается сам. Рекомендую.
2. **Render** (вариант A) — бесплатно и без сервера, но первый вход ~30 секунд
   из-за засыпания.
3. Свой ПК + туннель — только для быстрой пробы: адрес меняется при каждом запуске.

После развёртывания соберите архив клиента под этот адрес:

```bat
python deploy\make_client_package.py wss://203.0.113.10.sslip.io/ws
```

Получится `release\OMEGA-Messenger-<адрес>.zip` — внутри `OmegaClient.exe`,
`omega_config.json` с уже вписанным адресом и инструкция. Этот файл и
отправляйте.

---

## A. Render (бесплатно, проще всего)

1. Зарегистрируйтесь на [render.com](https://render.com) через GitHub.
2. Залейте проект в GitHub (ключи и история не попадут — они в `.gitignore`):

   ```bat
   cd C:\Users\meow\Desktop\мессенджер
   git init
   git add .
   git commit -m "Omega messenger"
   git branch -M main
   git remote add origin https://github.com/ВАШ_ЛОГИН/omega-messenger.git
   git push -u origin main
   ```

3. Render → **New → Web Service** → выберите репозиторий:
   * Language: **Python 3**
   * Build Command: `pip install -r requirements.txt`
   * Start Command: `python server.py`
   * Instance Type: **Free**
4. Через пару минут получите адрес вида `https://omega-xxxx.onrender.com`.
   Проверка: откройте его в браузере — должно быть `Omega E2E server is running`.
5. В клиенте (окно входа) адрес сервера: `wss://omega-xxxx.onrender.com/ws`.

В репозитории уже лежит `deploy/render.yaml` — можно вместо шагов 3–4 сделать
**New → Blueprint** и указать репозиторий.

Особенности бесплатного плана: сервис засыпает после 15 минут без соединений
(первое подключение ~30–60 секунд), файл `keyring.json` пропадает при
перезапуске — закреплённые ключи сбросятся, собеседники заново подтвердят
отпечатки. Для постоянного хранения нужен платный диск (`/data` + переменная
`OMEGA_KEYRING=/data/keyring.json`).

---

## B. Oracle Cloud Always Free (бесплатно навсегда, нужна карта)

Виртуальная машина, которая не засыпает. Карта нужна только для проверки
личности, списаний на Always Free нет.

1. Регистрация на [cloud.oracle.com](https://cloud.oracle.com), регион поближе
   (например, Frankfurt).
2. **Compute → Instances → Create**: образ Ubuntu 22.04, shape `VM.Standard.A1.Flex`
   (Ampere, 1–2 OCPU, 6 ГБ) или `VM.Standard.E2.1.Micro`.
3. В **Security List** подсети откройте входящие порты 80 и 443.
4. На машине:

   ```bash
   sudo apt update && sudo apt install -y python3-venv git
   git clone https://github.com/ВАШ_ЛОГИН/omega-messenger.git /opt/omega
   cd /opt/omega
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   ```

5. Служба `/etc/systemd/system/omega.service`:

   ```ini
   [Unit]
   Description=Omega messenger server
   After=network.target

   [Service]
   WorkingDirectory=/opt/omega
   Environment=OMEGA_KEYRING=/opt/omega/keyring.json
   ExecStart=/opt/omega/.venv/bin/python server.py --host 127.0.0.1 --port 8080
   Restart=always
   User=ubuntu

   [Install]
   WantedBy=multi-user.target
   ```

   ```bash
   sudo systemctl daemon-reload && sudo systemctl enable --now omega
   ```

6. HTTPS/WSS через Caddy (сам получает сертификат):

   ```bash
   sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
   curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
   echo "deb https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" | sudo tee /etc/apt/sources.list.d/caddy-stable.list
   sudo apt update && sudo apt install -y caddy
   ```

   `/etc/caddy/Caddyfile`:

   ```
   omega.example.com {
       reverse_proxy 127.0.0.1:8080
   }
   ```

   `sudo systemctl reload caddy`. В клиенте: `wss://omega.example.com/ws`.

---

## C. Свой ПК + Cloudflare Tunnel (работает сегодня, без аккаунтов)

Публичный `https://` адрес для сервера на домашнем компьютере, без проброса
портов на роутере.

1. Установите туннель:

   ```bat
   winget install --id Cloudflare.cloudflared
   ```

2. Запустите `deploy\share_from_home.bat` — он поднимет `OmegaServer.exe`
   (или `python server.py`) и туннель.
3. В консоли появится адрес `https://что-то.trycloudflare.com`.
   В клиенте указывайте `wss://что-то.trycloudflare.com/ws`.

Особенности: адрес меняется при каждом запуске, компьютер должен быть включён,
скорость зависит от домашнего интернета. Зато `keyring.json` и офлайн-очередь
живут на вашем диске и никуда не деваются.

### Готовый скрипт

```bat
deploy\cloudflared-tunnel.bat
```

Сам скачает `cloudflared` в `tools\`, поднимет `OmegaServer.exe` на 8080, если
тот ещё не запущен, и покажет адрес. Собеседникам — `wss://<адрес>/ws`.

### Если не подключается (ошибка 7844)

Cloudflare Tunnel ходит к своему Edge через **порт 7844** (UDP и TCP). Часть
провайдеров и корпоративных сетей его блокируют — тогда в логе видно:

```
ERR Failed to dial a quic connection ... timeout
TCP Connectivity  ...  FAIL  HTTP/2 connection is blocked or unreachable
ERROR: Allow outbound QUIC traffic on port 7844 or use HTTP2.
```

Что делать по порядку:

1. Запустить через HTTP/2 — иногда проходит там, где заблокирован UDP:

   ```bat
   deploy\cloudflared-tunnel.bat http2
   ```

2. Если и это не помогло — порт 7844 закрыт наглухо. Варианты:
   * **ngrok** (ходит по 443): зарегистрироваться, `ngrok config add-authtoken …`,
     `ngrok http 8080` → адрес вида `https://xxxx.ngrok-free.app`,
     в клиенте `wss://xxxx.ngrok-free.app/ws`;
   * развернуть сервер на Render (вариант A) — туннель вообще не нужен;
   * попробовать другую сеть: мобильный интернет с телефона (раздача Wi-Fi)
     обычно не блокирует 7844.

Проверить, открыт ли порт у вас: `Test-NetConnection region1.v2.argotunnel.com -Port 7844`
(в PowerShell). Если `TcpTestSucceeded: False` — туннель не заработает.

---

## D. Обычный VPS (самый предсказуемый)

Любой VPS с Ubuntu (Timeweb, Aeza, Reg.ru, Hetzner) + Docker:

```bash
git clone https://github.com/ВАШ_ЛОГИН/omega-messenger.git /opt/omega && cd /opt/omega
docker build -t omega .
docker run -d --restart=always --name omega \
  -p 127.0.0.1:8080:8080 \
  -v /opt/omega/data:/data \
  -e OMEGA_KEYRING=/data/keyring.json \
  omega
```

Дальше Caddy из варианта B (или nginx) для `wss://`. Клиент:
`wss://ваш-домен/ws`.

---

## Проверка после развёртывания

```bat
curl https://ваш-адрес/
```

Должно вернуться `Omega E2E server is running. Online: N, known: M`.

Проверка WebSocket:

```bat
python deploy\check_server.py wss://ваш-адрес/ws
```

Проще всего: запустить `dist\OmegaMessenger.exe`, ввести ник и адрес
`wss://ваш-адрес/ws` — если в шапке появился статус «в сети», всё работает.

## Что важно не потерять

* `keyring.json` — единственное состояние сервера. При переезде скопируйте его,
  иначе все закреплённые ключи сбросятся и клиенты покажут предупреждение
  «ключ изменился».
* `pin_keys` включён по умолчанию: под чужим ником с другим ключом войти нельзя.
  Сбросить ключ ника: `python server.py --reset-key Ник`.
* Сервер не видит содержимое переписки, но видит метаданные (кто, кому, когда).
  Не выкладывайте адрес сервера в открытый доступ без необходимости.
