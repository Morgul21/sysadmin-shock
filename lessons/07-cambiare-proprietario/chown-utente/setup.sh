groupadd ufficio
groupadd tecnici
mkdir -p "$EX"
chmod 755 "$EX"
echo "report di prova" > "$EX/report.txt"
chown "root:$(pick ufficio tecnici app)" "$EX/report.txt"
chmod 640 "$EX/report.txt"
save report.group "$(stat -c %G "$EX/report.txt")"
