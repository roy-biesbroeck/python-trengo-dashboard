#!/data/data/com.termux/files/usr/bin/bash
exec > ~/boot.log 2>&1
echo "Boot script gestart: $(date)"
sshd
termux-wake-lock

# Keepalive: box is headless (geen scherm) -> Android dozed 's nachts en de wifi-link
# valt weg -> dashboard onbereikbaar tot power-cycle. Lichte ping elke 20s houdt de
# wifi-link wakker. setsid zodat de loop het einde van dit script overleeft.
setsid sh -c 'while true; do ping -c 1 -w 5 192.168.0.1 > /dev/null 2>&1; sleep 20; done' > /dev/null 2>&1 < /dev/null &

pkill -9 python 2>/dev/null
sleep 2

cd ~/dashboard
python app.py &
echo "Flask gestart, wachten tot server reageert..."

# Wacht tot Flask reageert
until python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000', timeout=1)" 2>/dev/null; do
    sleep 1
done
echo "Flask klaar, browser openen..."

am start -a android.intent.action.VIEW -d "http://localhost:5000"
echo "Klaar."
