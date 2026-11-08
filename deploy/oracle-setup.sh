#!/usr/bin/env bash
# Установка сервера OMEGA на Ubuntu (Oracle Cloud Always Free и любой VPS).
#
# Запуск из папки проекта:
#     sudo bash deploy/oracle-setup.sh
#
# Открывает порт 8080, ставит systemd-службу и печатает адрес для клиента.
# TLS и домен не нужны: клиент ходит по ws://IP:8080/ws, переписка и так
# зашифрована на устройствах.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8080}"
SERVICE=/etc/systemd/system/omega.service
RUN_USER="${SUDO_USER:-root}"

echo "== OMEGA: установка в $APP_DIR (порт $PORT) =="

if [ ! -f "$APP_DIR/server.py" ]; then
    echo "В $APP_DIR нет server.py — запустите скрипт из папки проекта."
    exit 1
fi

# --- зависимости ---
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv curl >/dev/null

if [ ! -d "$APP_DIR/.venv" ]; then
    python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet "aiohttp>=3.9"

# служба работает не от root — отдаём ей папку с данными
if [ "$RUN_USER" != "root" ]; then
    chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR" 2>/dev/null || true
fi

# --- служба ---
cat > "$SERVICE" <<EOF
[Unit]
Description=Omega E2E messenger server
After=network.target

[Service]
WorkingDirectory=$APP_DIR
Environment=OMEGA_KEYRING=$APP_DIR/keyring.json
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/server.py --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3
User=$RUN_USER

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now omega
sleep 3
systemctl --no-pager --lines=5 status omega || true

# --- firewall (если включён) ---
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    ufw allow "$PORT"/tcp >/dev/null || true
    echo "ufw: порт $PORT открыт"
elif command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --add-port="$PORT"/tcp --permanent >/dev/null 2>&1 || true
    firewall-cmd --reload >/dev/null 2>&1 || true
fi
# iptables (в Oracle Ubuntu по умолчанию правила есть)
iptables -I INPUT -p tcp --dport "$PORT" -j ACCEPT 2>/dev/null || true

# --- проверка и адрес ---
IP="$(curl -s --max-time 8 https://api.ipify.org || hostname -I | awk '{print $1}')"
sleep 1
if curl -s --max-time 5 "http://127.0.0.1:$PORT/" | grep -q "Omega"; then
    echo
    echo "======================================================"
    echo " Сервер работает."
    echo " Адрес для клиентов:  ws://$IP:$PORT/ws"
    echo
    echo " НЕ ЗАБУДЬТЕ открыть порт $PORT в панели Oracle:"
    echo "   Networking -> Virtual Cloud Networks -> Security List"
    echo "   -> Add Ingress Rule: Source 0.0.0.0/0, TCP, port $PORT"
    echo "======================================================"
else
    echo "Сервер не ответил локально. Логи: journalctl -u omega -n 40"
    exit 1
fi
