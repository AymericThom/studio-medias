#!/usr/bin/env bash
# Installe Studio Médias sur un serveur Linux gratuit (Oracle Cloud Always Free, Google Cloud e2-micro…)
# Utilisation, dans le dossier du studio copié sur le serveur :   bash serveur/installer_serveur.sh
# Ensuite le studio tourne 24h/24 et redémarre tout seul. Une adresse https publique est créée via Cloudflare
# (gratuit, sans nom de domaine). PENSE À DÉFINIR UN MOT DE PASSE dans Réglages avant de partager l'adresse.
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="$(pwd)"

echo "== Paquets système"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv curl xvfb

echo "== Environnement Python"
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "== Navigateur pour lire les sites qui bloquent les robots"
sudo .venv/bin/python -m playwright install-deps chromium
.venv/bin/python -m playwright install chromium

echo "== Service du studio (démarre avec le serveur, redémarre en cas de souci)"
sudo tee /etc/systemd/system/studio-medias.service >/dev/null <<EOF
[Unit]
Description=Studio Medias
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$DIR
ExecStart=/usr/bin/xvfb-run -a $DIR/.venv/bin/python app.py --no-browser
Restart=always
RestartSec=10
User=$USER

[Install]
WantedBy=multi-user.target
EOF

echo "== Tunnel Cloudflare (adresse https publique gratuite, aucun port à ouvrir)"
ARCH="$(dpkg --print-architecture)"
curl -fsSL -o /tmp/cloudflared.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb"
sudo dpkg -i /tmp/cloudflared.deb
sudo tee /etc/systemd/system/studio-tunnel.service >/dev/null <<EOF
[Unit]
Description=Tunnel Cloudflare pour Studio Medias
After=studio-medias.service

[Service]
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate --url http://localhost:8765
Restart=always
RestartSec=10
User=$USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now studio-medias studio-tunnel
sleep 12
echo
echo "== C'est prêt. Adresse publique du studio :"
journalctl -u studio-tunnel --no-pager | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 || true
echo "(si rien ne s'affiche : journalctl -u studio-tunnel | grep trycloudflare)"
echo "L'adresse change si le serveur redémarre. Pour une adresse fixe : un nom de domaine (~10 €/an) + tunnel Cloudflare nommé."
