#!/usr/bin/env bash
set -e

mkdir -p /home/abc/Desktop /config /workspace
chown -R abc:abc /home/abc /config /workspace || true

export DISPLAY=:1
export RESOLUTION="${RESOLUTION:-1920x1080}"
export HOME="/home/abc"

# 1. Start Virtual Framebuffer
rm -rf /tmp/.X1-lock /tmp/.X11-unix/X1
Xvfb :1 -screen 0 "${RESOLUTION}x24" -ac +extension GLX +render -noreset &
sleep 1

# 2. Set default mouse pointer & GTK theme
su -c "
  export DISPLAY=:1
  xsetroot -cursor_name left_ptr -display :1 || true
  xfconf-query -c xsettings -p /Gtk/CursorThemeName -s Adwaita --create -t string || true
  xfconf-query -c xsettings -p /Gtk/CursorThemeSize -s 24 --create -t int || true
" abc || true

# 3. Create desktop shortcuts
GATEWAY=$(ip route 2>/dev/null | awk '/default/ {print $3; exit}' || echo "")
GATEWAY="${GATEWAY:-172.17.0.1}"

# Initialize standard user directories (Downloads, Documents, etc) if missing
xdg-user-dirs-update

# Setup Python venv for Hermes Agent if it doesn't exist
if [ ! -d "/home/abc/hermes_venv" ]; then
    python3 -m venv /home/abc/hermes_venv
    # Extract dependencies from pyproject.toml and install them directly to avoid macOS mount "Resource deadlock" errors
    deps=$(grep -E '^[[:space:]]*"(openai|certifi|python-dotenv|fire|httpx|rich|tenacity|pyyaml|ruamel\.yaml|requests|jinja2|pydantic|prompt_toolkit|croniter|packaging|Markdown|PyJWT|urllib3|cryptography|psutil|websockets|pathspec|fastapi|uvicorn|python-multipart|ptyprocess|Pillow).*",' /workspace/hermes-agent/pyproject.toml | sed 's/^[[:space:]]*"//g' | sed 's/".*$//g')
    /home/abc/hermes_venv/bin/pip install $deps || true
fi

cat > /home/abc/Desktop/Hermes.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Hermes Agent
Exec=google-chrome --no-sandbox --app=http://host.docker.internal:9119
Icon=utilities-terminal
Terminal=false
EOF

cat > /home/abc/Desktop/OpenClaw.desktop <<EOF
[Desktop Entry]
Type=Application
Name=OpenClaw
Exec=google-chrome --no-sandbox http://host.docker.internal:5173
Icon=internet-web-browser
Terminal=false
EOF

cat > /home/abc/Desktop/Chrome.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Google Chrome
Exec=google-chrome --no-sandbox
Icon=google-chrome
Terminal=false
EOF

cat > /home/abc/Desktop/VSCode.desktop <<EOF
[Desktop Entry]
Type=Application
Name=VS Code
Exec=code --no-sandbox /workspace
Icon=com.visualstudio.code
Terminal=false
EOF

cat > /home/abc/Desktop/Terminal.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Terminal
Exec=xfce4-terminal
Icon=utilities-terminal
Terminal=false
EOF

chmod +x /home/abc/Desktop/*.desktop || true
chown -R abc:abc /home/abc/Desktop || true

# 4. Start XFCE4 session
su -c "export DISPLAY=:1; exec startxfce4" abc &
sleep 2

# 5. Start x11vnc with native cursor tracking and XKB for proper typing
x11vnc -display :1 -nopw -forever -shared -rfbport 5900 -cursor arrow -noxrecord -noxfixes -noxdamage -xkb &
sleep 1

# 6. Start noVNC websockify web server on port 3000
exec websockify --web=/usr/share/novnc 3000 127.0.0.1:5900
