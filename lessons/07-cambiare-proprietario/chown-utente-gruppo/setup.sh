groupadd tecnici
useradd -M -N -g tecnici anna
mkdir -p "$EX"
chmod 755 "$EX"
printf '[server]\nporta = 8080\n' > "$EX/config.ini"
chmod "$(pick 640 600 660)" "$EX/config.ini"
save config.mode "$(mode "$EX/config.ini")"
