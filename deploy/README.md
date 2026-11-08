# Где разместить сервер OMEGA

Серверу нужен только Python 3.10+ и открытый порт. Состояние — один файл
`keyring.json` (закреплённые публичные ключи) и офлайн-очередь в памяти.
TLS можно не настраивать на самом сервере: у большинства хостингов HTTPS/WSS
терминируется на их прокси.

Клиент всегда подключается по адресу `wss://<домен>/ws` (или `ws://IP:8080/ws`,
если сервер без TLS в локальной сети).

| Вариант | Цена | Время | Плюсы | Минусы |
|---|---|---|---|---|
| A. Render | 0 ₽ | 10 мин | Ничего не администрировать | Засыпает через 15 мин; **у части провайдеров РФ открывается только через VPN** |
| B. Oracle Cloud Always Free | 0 ₽ | 40 мин | Постоянная VM, полный контроль | Нужна карта для верификации, своя возня с TLS |
| C. Свой ПК + Cloudflare Tunnel | 0 ₽ | 5 мин | Работает сегодня, данные у вас | ПК включён, адрес меняется |
| D. VPS в РФ (без TLS) | ~200–400 ₽/мес | 10 мин | **Работает без VPN**, адрес постоянный, без домена и сертификатов | Платно |

## Что выбрать для показа работодателю

Если у заказчика сеть, где `onrender.com` не открывается без VPN (частая
история в РФ), единственный надёжный вариант — **VPS в РФ с адресом
`ws://IP:8080/ws`**: ни домена, ни сертификата не нужно, TLS не требуется,
потому что переписка и так зашифрована на клиентах.

1. **VPS в РФ + `docker-compose-simple.yml`** — см. раздел E ниже. 10 минут,
   200–350 ₽/мес, работает без VPN. Рекомендую.
2. **VPS + HTTPS и домен** — [vps-quickstart.md](vps-quickstart.md), если нужен
   красивый адрес `wss://…`.
3. **Render** (вариант A) — бесплатно, но у части провайдеров только через VPN.
4. Свой ПК + туннель — только для быстрой пробы: адрес меняется при каждом запуске.

## E. VPS в РФ без TLS (работает без VPN)

1. Купите VPS: Timeweb Cloud, Aeza, Beget — Ubuntu 24.04, 1 vCPU, 1 ГБ.
   Запишите IP, например `203.0.113.10`.
2. Поставьте Docker:

   ```bash
   ssh root@203.0.113.10
   curl -fsSL https://get.docker.com | sh
   ```

3. Залейте проект с компьютера (в новом окне PowerShell):

   ```powershell
   scp -r "C:\Users\meow\Desktop\мессенджер" root@203.0.113.10:/opt/omega
   ```

4. Запустите:

   ```bash
   cd /opt/omega && mkdir -p data
   docker compose -f docker-compose-simple.yml up -d --build
   ufw allow 8080/tcp || true
   ```

5. Проверка: `curl http://203.0.113.10:8080/` → `Omega E2E server is running`.

6. Адрес для клиента: **`ws://203.0.113.10:8080/ws`** — без VPN, без домена.

7. Соберите архив клиента под этот адрес:

   ```bat
   python deploy\make_client_package.py ws://203.0.113.10:8080/ws
   ```

Порт 8080 должен быть открыт и в панели хостинга (Security Group / Firewall),
если там есть такая настройка.

### Без Docker (ещё проще, если Docker не нужен)

```bash
apt update && apt install -y python3-venv
mkdir -p /opt/omega && cd /opt/omega
python3 -m venv .venv && .venv/bin/pip install aiohttp
# скопируйте server.py и config.py в /opt/omega (scp)
nohup .venv/bin/python server.py --host 0.0.0.0 --port 8080 &
```

Для автозапуска после перезагрузки — systemd-юнит из
[vps-quickstart.md](vps-quickstart.md) (замените путь и уберите `--host 127.0.0.1`).

После развёртывания соберите архив клиента под этот адрес:

```bat
python deploy\make_client_package.py wss://203.0.113.10.sslip.io/ws
```

Получится `release\OMEGA-Messenger-<адрес>.zip` — внутри `OmegaClient.exe`,
`omega_config.json` с уже вписанным адресом и инструкция. Этот файл и
отправляйте.

---

## A. Render (бесплатно, проще всего)

Проект уже в git: репозиторий инициализирован, всё лишнее (ключи, exe, история)
в `.gitignore`. Осталось залить его на GitHub и создать сервис.

### 1. Репозиторий на GitHub

На [github.com](https://github.com) → **New repository** → имя `omega-messenger`,
**Public**, без README и .gitignore → **Create**.

Затем одним из способов:

**Способ А — скриптом:**

```bat
cd C:\Users\meow\Desktop\мессенджер
deploy\push-to-github.bat https://github.com/ВАШ_ЛОГИН/omega-messenger.git
```

При первом запуске откроется окно входа GitHub (или спросит токен).

**Способ Б — вручную:**

```bat
cd C:\Users\meow\Desktop\мессенджер
git remote add origin https://github.com/ВАШ_ЛОГИН/omega-messenger.git
git branch -M main
git push -u origin main
```

### 2. Сервис на Render

Зарегистрируйтесь на [render.com](https://render.com) через GitHub, затем:

**Вариант Blueprint (быстрее):** **New → Blueprint** → выберите репозиторий →
Render сам прочитает `render.yaml` → **Apply**.

**Вариант вручную:** **New → Web Service** → репозиторий →
Language **Python 3**, Build Command `pip install -r requirements-server.txt`,
Start Command `python server.py`, Instance Type **Free**, Region **Frankfurt** →
**Create Web Service**.

Через 2–4 минуты будет адрес `https://omega-xxxx.onrender.com`.

### 3. Проверка

```bat
curl https://omega-xxxx.onrender.com/
python deploy\check_server.py wss://omega-xxxx.onrender.com/ws
```

Первая команда вернёт `Omega E2E server is running`, вторая — `OK`.

### 4. Клиент для показа

```bat
python deploy\make_client_package.py wss://omega-xxxx.onrender.com/ws
```

Получится архив с уже вписанным адресом — его и отправляйте.

### 5. Чтобы сервис не засыпал

Бесплатный инстанс засыпает после 15 минут без запросов, и первый вход
занимает 30–60 секунд. Лечится бесплатным пингером:

1. [cron-job.org](https://cron-job.org) → Create cronjob;
2. URL: `https://omega-xxxx.onrender.com/`, каждые **10 минут**;
3. всё, сервис просыпается сам.

В бесплатном плане 750 часов инстанса в месяц, а в месяце максимум 744 — один
круглосуточный сервис помещается.

### Особенности бесплатного плана

* засыпает без пингов (первое подключение ~30–60 с; клиент переподключается сам);
* `keyring.json` стирается при перезапуске/редеплое — закреплённые ключи
  сбрасываются, собеседники заново подтвердят отпечатки;
* офлайн-очередь живёт в памяти и при засыпании пропадает;
* для постоянного хранения нужен платный диск: `OMEGA_KEYRING=/data/keyring.json`
  и диск, смонтированный в `/data`.

---

## B. Oracle Cloud Always Free (бесплатно навсегда, нужна карта)

Виртуальная машина, которая не засыпает и работает без VPN.
Карта нужна только для проверки личности, списаний на Always Free нет.

1. Регистрация на [cloud.oracle.com](https://cloud.oracle.com), регион поближе
   (например, Frankfurt).
2. **Compute → Instances → Create**: Ubuntu 24.04.
   * `VM.Standard.A1.Flex` (Ampere, 1–2 OCPU, 6 ГБ) — если пишет
     «out of host capacity», попробуйте другое Availability Domain или
     `VM.Standard.E2.1.Micro` (AMD, 1 ГБ).
   * Галочку «Assign a public IPv4 address» оставьте включённой.
3. **Откройте порт 8080** (без этого снаружи не подключиться):
   **Networking → Virtual Cloud Networks → ваша VCN → Security Lists →
   Default Security List → Add Ingress Rule**:
   Source `0.0.0.0/0`, IP Protocol `TCP`, Destination Port Range `8080`.

4. На машине (подключитесь: `ssh ubuntu@IP`, ключ Oracle даёт при создании):

   ```bash
   sudo apt update && sudo apt install -y git
   git clone https://github.com/danil84-spec/omega-messenger.git /opt/omega
   cd /opt/omega
   sudo bash deploy/oracle-setup.sh
   ```

   Скрипт сам поставит Python-окружение, создаст службу `omega`,
   включит автозапуск, откроет порт в firewall и напечатает адрес вида
   `ws://130.61.x.x:8080/ws`.

5. Проверка (с вашего компьютера):

   ```powershell
   curl http://IP:8080/
   python deploy\check_server.py ws://IP:8080/ws
   ```

6. Клиент для заказчика собирается под этот адрес:

   ```bat
   python deploy\make_client_package.py --dir ws://IP:8080/ws
   ```

   TLS и домен не нужны: переписка шифруется на устройствах, `ws://` лишь
   открывает метаданные провайдеру. Если позже захотите `wss://` — в
   [vps-quickstart.md](vps-quickstart.md) есть Caddy, который сам получает
   сертификат.

### Полезное по Oracle

* Служба: `systemctl status omega`, логи: `journalctl -u omega -f`.
* Перезапуск: `sudo systemctl restart omega`.
* Ключи закрепляются в `/opt/omega/keyring.json` — делайте копию.
* Если `curl` снаружи молчит, а локально `http://127.0.0.1:8080/` отвечает —
  почти всегда забыли пункт 3 (Security List).

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
