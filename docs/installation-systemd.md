# Установка без Docker: venv + systemd

## Системные зависимости Debian/Ubuntu

```bash
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-dev \
  build-essential libpq-dev libmagic1 ffmpeg
```

## Установка

```bash
sudo useradd --system --create-home --home-dir /opt/pymatrix-max pymatrix-max
sudo -u pymatrix-max git clone https://github.com/NijazKa/pymatrix-max.git /opt/pymatrix-max/app
cd /opt/pymatrix-max/app

sudo -u pymatrix-max python3 -m venv .venv
sudo -u pymatrix-max .venv/bin/python -m pip install --upgrade pip setuptools wheel
sudo -u pymatrix-max .venv/bin/python -m pip install --no-build-isolation .

sudo -u pymatrix-max mkdir -p data
sudo -u pymatrix-max cp example-config.yaml data/config.yaml
```

Для systemd обычно используются:

```yaml
homeserver:
  address: http://127.0.0.1:8008

appservice:
  address: http://127.0.0.1:29320
```

Сгенерируйте регистрацию:

```bash
sudo -u pymatrix-max .venv/bin/python -m mautrix_max \
  -g -c data/config.yaml -r data/registration.yaml
```

Подключите `data/registration.yaml` к Synapse и перезапустите его.

## Unit-файл

`/etc/systemd/system/pymatrix-max.service`:

```ini
[Unit]
Description=pymatrix-max Matrix ↔ MAX bridge
After=network-online.target matrix-synapse.service
Wants=network-online.target

[Service]
Type=simple
User=pymatrix-max
Group=pymatrix-max
WorkingDirectory=/opt/pymatrix-max/app
ExecStart=/opt/pymatrix-max/app/.venv/bin/python -m mautrix_max -c data/config.yaml -r data/registration.yaml
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/pymatrix-max/app/data

[Install]
WantedBy=multi-user.target
```

Запуск:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pymatrix-max
sudo systemctl status pymatrix-max
sudo journalctl -u pymatrix-max -f
```
