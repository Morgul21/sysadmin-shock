groupadd contabilita
useradd -M -N anna
mkdir -p "$EX"
chmod 755 "$EX"
printf 'voce;importo\naffitto;1200\n' > "$EX/bilancio.csv"
chown root:contabilita "$EX/bilancio.csv"
chmod 640 "$EX/bilancio.csv"
