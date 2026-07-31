#!/usr/bin/with-contenv bash
set -e

DESKTOP_DIR="/config/Desktop"
APP_DIR="/config/ClawApps"

mkdir -p "$DESKTOP_DIR" "$APP_DIR"
AUTOSTART_DIR="/config/xfce4/autostart"
mkdir -p "$AUTOSTART_DIR"
PROFILE_DIR="/config/chromium-browser-profile-abc"
mkdir -p "$PROFILE_DIR"

# Detect Docker gateway IP (works inside containers to reach host services)
DOCKER_GATEWAY=$(ip route | awk '/default/ {print $3; exit}')
if [ -z "$DOCKER_GATEWAY" ]; then
  DOCKER_GATEWAY="172.17.0.1"
fi

# Make the local X11 session explicit so launchers inherit a valid display
# even when they are started from the desktop, the panel, or a helper script.
cat > /etc/profile.d/cloud-desktop.sh <<'EOF'
export DISPLAY="${DISPLAY:-:1}"
export XAUTHORITY="${XAUTHORITY:-/config/.Xauthority}"
EOF

if [ -f /opt/brave.com/brave/brave-browser ]; then
  sed -i 's|"$HERE/brave" "$@"|"$HERE/brave" --no-sandbox --disable-dev-shm-usage --disable-gpu "$@"|g' /opt/brave.com/brave/brave-browser || true
fi

cat > "$AUTOSTART_DIR/desktop-appearance.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Desktop Appearance
Exec=sh -lc 'sleep 2; xfconf-query -c xfce4-panel -p /panels/panel-1/size -s 48 >/dev/null 2>&1; xfconf-query -c xfce4-panel -p /panels/panel-1/icon-size -s 36 >/dev/null 2>&1; xfconf-query -c xfwm4 -p /general/use_compositing -s false >/dev/null 2>&1; xfconf-query -c xfce4-desktop -p /desktop-icons/style -s 2 >/dev/null 2>&1; xset r rate 180 40 >/dev/null 2>&1; xfdesktop --reload >/dev/null 2>&1 || true'
X-GNOME-Autostart-enabled=true
EOF

cat > "$APP_DIR/open-hermes.sh" <<'EOF'
#!/usr/bin/env bash
GATEWAY=$(ip route | awk '/default/ {print $3; exit}')
GATEWAY="${GATEWAY:-172.19.0.1}"
DISPLAY_NUM="${DISPLAY:-:1}"
XAUTH="${XAUTHORITY:-/config/.Xauthority}"

/config/ClawApps/open-browser.sh "http://${GATEWAY}:9119" &
exec env DISPLAY="$DISPLAY_NUM" XAUTHORITY="$XAUTH" xfce4-terminal \
  --title="Hermes Agent AI" \
  --geometry=120x35 \
  --working-directory="/workspace" \
  -e "bash -c 'python3 /workspace/hermes-agent/cli.py; exec bash'"
EOF

cat > "$APP_DIR/open-openclaw.sh" <<'EOF'
#!/usr/bin/env bash
GATEWAY=$(ip route | awk '/default/ {print $3; exit}')
GATEWAY="${GATEWAY:-172.19.0.1}"
exec /config/ClawApps/open-browser.sh "http://${GATEWAY}:5173"
EOF

cat > "$APP_DIR/open-desktop.sh" <<'EOF'
#!/usr/bin/env bash
GATEWAY=$(ip route | awk '/default/ {print $3; exit}')
GATEWAY="${GATEWAY:-172.19.0.1}"
exec /config/ClawApps/open-browser.sh "http://${GATEWAY}:3010"
EOF

cat > "$APP_DIR/open-browser.sh" <<'EOF'
#!/usr/bin/env bash
TARGET="${1:-https://www.google.com}"
PROFILE_DIR="/config/chromium-browser-profile-abc"
DISPLAY_NUM="${DISPLAY:-:1}"
XAUTH="${XAUTHORITY:-/config/.Xauthority}"
mkdir -p "$PROFILE_DIR"
rm -rf /config/*/Singleton*

if command -v brave-browser >/dev/null 2>&1; then
  exec env DISPLAY="$DISPLAY_NUM" XAUTHORITY="$XAUTH" brave-browser \
    --new-window \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --user-data-dir="$PROFILE_DIR" \
    "$TARGET"
elif command -v chromium >/dev/null 2>&1; then
  exec env DISPLAY="$DISPLAY_NUM" XAUTHORITY="$XAUTH" chromium \
    --new-window \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
  --user-data-dir="$PROFILE_DIR" \
    "$TARGET"
elif command -v chromium-browser >/dev/null 2>&1; then
  exec env DISPLAY="$DISPLAY_NUM" XAUTHORITY="$XAUTH" chromium-browser \
    --new-window \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --user-data-dir="$PROFILE_DIR" \
    "$TARGET"
elif command -v firefox >/dev/null 2>&1; then
  exec env DISPLAY="$DISPLAY_NUM" XAUTHORITY="$XAUTH" firefox --new-window "$TARGET"
else
  exec env DISPLAY="$DISPLAY_NUM" XAUTHORITY="$XAUTH" xdg-open "$TARGET"
fi
EOF

cat > "$APP_DIR/open-terminal.sh" <<'EOF'
#!/usr/bin/env bash
DISPLAY_NUM="${DISPLAY:-:1}"
XAUTH="${XAUTHORITY:-/config/.Xauthority}"
if command -v xfce4-terminal >/dev/null 2>&1; then
  exec env DISPLAY="$DISPLAY_NUM" XAUTHORITY="$XAUTH" xfce4-terminal
elif command -v xterm >/dev/null 2>&1; then
  exec env DISPLAY="$DISPLAY_NUM" XAUTHORITY="$XAUTH" xterm
else
  exec sh
fi
EOF

cat > "$APP_DIR/desktop-automation.sh" <<'EOF'
#!/usr/bin/env bash
set -e
echo "Available tools:"
for tool in xdotool wmctrl xfce4-terminal chromium firefox; do
  if command -v "$tool" >/dev/null 2>&1; then
    echo "  - $tool"
  fi
done
echo
echo "Examples:"
echo "  xdotool search --name 'Terminal' windowactivate"
echo "  xdotool search --name 'Browser' windowactivate"
echo "  wmctrl -l"
echo "  xdg-open https://www.google.com"
EOF

chmod +x "$APP_DIR/open-hermes.sh" "$APP_DIR/open-openclaw.sh" "$APP_DIR/open-desktop.sh" "$APP_DIR/open-browser.sh" "$APP_DIR/open-terminal.sh" "$APP_DIR/desktop-automation.sh"

cat > "$AUTOSTART_DIR/browser.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Browser Autostart
Exec=env DISPLAY=:1 XAUTHORITY=/config/.Xauthority brave-browser --new-window --no-sandbox --disable-dev-shm-usage --disable-gpu --user-data-dir=/config/brave-browser-profile-abc https://www.google.com
X-GNOME-Autostart-enabled=true
EOF

cat > "$DESKTOP_DIR/Hermes.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Hermes
Exec=/config/ClawApps/open-hermes.sh
Icon=utilities-terminal
Terminal=false
Categories=Network;
StartupNotify=true
EOF

cat > "$DESKTOP_DIR/OpenClaw.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=OpenClaw
Exec=/config/ClawApps/open-openclaw.sh
Icon=internet-web-browser
Terminal=false
Categories=Network;
StartupNotify=true
EOF

cat > "$DESKTOP_DIR/CloudDesktop.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Cloud Desktop
Exec=/config/ClawApps/open-desktop.sh
Icon=computer
Terminal=false
Categories=Utility;
StartupNotify=true
EOF

cat > "$DESKTOP_DIR/Brave.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Brave Web Browser
Exec=/usr/bin/brave-browser-stable %u
Icon=brave-browser
Terminal=false
Categories=Network;WebBrowser;
StartupWMClass=Brave-browser
EOF

cat > "$DESKTOP_DIR/Firefox.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Firefox Web Browser
Exec=firefox --new-window %u
Icon=firefox
Terminal=false
Categories=Network;WebBrowser;
EOF

cat > "$DESKTOP_DIR/Chromium.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Chromium Web Browser
Exec=chromium --no-sandbox --disable-dev-shm-usage %u
Icon=chromium-browser
Terminal=false
Categories=Network;WebBrowser;
EOF

cat > "$DESKTOP_DIR/GnomeWeb.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=GNOME Web (Epiphany)
Exec=epiphany %u
Icon=org.gnome.Epiphany
Terminal=false
Categories=Network;WebBrowser;
EOF

cat > "$DESKTOP_DIR/Terminal.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Terminal
Exec=env DISPLAY=:1 XAUTHORITY=/config/.Xauthority xfce4-terminal
Icon=utilities-terminal
Terminal=false
Categories=System;TerminalEmulator;
StartupWMClass=xfce4-terminal
EOF

cat > "$DESKTOP_DIR/VSCode.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=VS Code
Exec=env DISPLAY=:1 XAUTHORITY=/config/.Xauthority code --no-sandbox --user-data-dir=/config/vscode-data /workspace
Icon=com.visualstudio.code
Terminal=false
Categories=Development;IDE;
StartupWMClass=code
EOF

cat > "$DESKTOP_DIR/FileManager.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=File Manager
Exec=env DISPLAY=:1 XAUTHORITY=/config/.Xauthority thunar /workspace
Icon=system-file-manager
Terminal=false
Categories=System;Core;
StartupWMClass=thunar
EOF

cat > "$DESKTOP_DIR/TaskManager.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Task Manager
Exec=env DISPLAY=:1 XAUTHORITY=/config/.Xauthority xfce4-taskmanager
Icon=utilities-system-monitor
Terminal=false
Categories=System;
StartupWMClass=xfce4-taskmanager
EOF

cat > "$DESKTOP_DIR/Automation.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Desktop Automation
Exec=/config/ClawApps/desktop-automation.sh
Icon=preferences-system
Terminal=true
Categories=Utility;
EOF

chmod +x "$DESKTOP_DIR/"*.desktop
mkdir -p /config/.hermes
chown -R abc:abc "$DESKTOP_DIR" "$APP_DIR" "$AUTOSTART_DIR" "$PROFILE_DIR" /config/.hermes || true
chmod -R 777 /config/.hermes || true
