# Un job dei report carica tutto lo storico in memoria e non lo rilascia più.
mkdir -p /opt/report
cat > /opt/report/build-report.py <<'EOF'
"""Job dei report: carica lo storico in memoria per aggregarlo."""
import time

history = b"\x01" * (200 * 2**20)
while True:
    time.sleep(3600)
EOF
setsid nohup python3 /opt/report/build-report.py < /dev/null > /dev/null 2>&1 &

# Aspetta che la memoria sia occupata davvero, altrimenti il check potrebbe passare.
for _ in $(seq 40); do
    rss=$(ps -C python3 -o rss= | sort -n | tail -1)
    [ "${rss:-0}" -gt 190000 ] && exit 0
    sleep 0.5
done
echo "il job non ha occupato la memoria" >&2
exit 1
