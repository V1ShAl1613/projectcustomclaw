#!/usr/bin/with-contenv bash
set -e

DESKTOP_DIR="/config/Desktop"
APP_DIR="/config/ClawApps"

mkdir -p "$DESKTOP_DIR" "$APP_DIR"
AUTOSTART_DIR="/config/xfce4/autostart"
mkdir -p "$AUTOSTART_DIR"
PROFILE_DIR="/config/chromium-browser-profile-abc"
mkdir -p "$PROFILE_DIR"

cat > "$AUTOSTART_DIR/desktop-appearance.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Desktop Appearance
Exec=sh -lc 'sleep 2; xfconf-query -c xfce4-panel -p /panels/panel-1/size -s 48 >/dev/null 2>&1; xfconf-query -c xfce4-panel -p /panels/panel-1/icon-size -s 36 >/dev/null 2>&1; xfconf-query -c xfwm4 -p /general/use_compositing -s false >/dev/null 2>&1; xfconf-query -c xfce4-desktop -p /desktop-icons/style -s 0 >/dev/null 2>&1; xset r rate 180 40 >/dev/null 2>&1; xfdesktop --reload >/dev/null 2>&1 || true'
X-GNOME-Autostart-enabled=true
EOF

cat > "$APP_DIR/open-hermes.sh" <<'EOF'
#!/usr/bin/env bash
xdg-open http://host.docker.internal:9119
EOF

cat > "$APP_DIR/open-openclaw.sh" <<'EOF'
#!/usr/bin/env bash
xdg-open http://host.docker.internal:18789
EOF

cat > "$APP_DIR/open-desktop.sh" <<'EOF'
#!/usr/bin/env bash
xdg-open http://host.docker.internal:3010
EOF

cat > "$APP_DIR/open-browser.sh" <<'EOF'
#!/usr/bin/env bash
TARGET="${1:-https://www.google.com}"
PROFILE_DIR="/config/chromium-browser-profile-abc"
DISPLAY_NUM="${DISPLAY:-:1}"
XAUTH="${XAUTHORITY:-/config/.Xauthority}"
mkdir -p "$PROFILE_DIR"

if command -v chromium >/dev/null 2>&1; then
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

cat > "$DESKTOP_DIR/Hermes.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Hermes
Exec=/config/ClawApps/open-hermes.sh
Icon=utilities-terminal
Terminal=false
Categories=Network;
EOF

cat > "$DESKTOP_DIR/OpenClaw.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=OpenClaw
Exec=/config/ClawApps/open-openclaw.sh
Icon=internet-web-browser
Terminal=false
Categories=Network;
EOF

cat > "$DESKTOP_DIR/CloudDesktop.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Cloud Desktop
Exec=/config/ClawApps/open-desktop.sh
Icon=computer
Terminal=false
Categories=Utility;
EOF

cat > "$DESKTOP_DIR/Browser.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Browser
Exec=/config/ClawApps/open-browser.sh https://www.google.com
Icon=internet-web-browser
Terminal=false
Categories=Network;WebBrowser;
StartupWMClass=Chromium
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

cat > "$DESKTOP_DIR/Automation.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Desktop Automation
Exec=/config/ClawApps/desktop-automation.sh
Icon=preferences-system
Terminal=true
Categories=Utility;
EOF

cat > "$AUTOSTART_DIR/browser.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Browser Autostart
Exec=env DISPLAY=:1 XAUTHORITY=/config/.Xauthority /usr/bin/chromium --new-window --no-sandbox --disable-dev-shm-usage --disable-gpu --user-data-dir=/config/chromium-browser-profile-abc https://www.google.com
X-GNOME-Autostart-enabled=true
EOF

chmod +x "$DESKTOP_DIR/"*.desktop
chown -R abc:abc "$DESKTOP_DIR" "$APP_DIR" "$AUTOSTART_DIR" "$PROFILE_DIR" || true
