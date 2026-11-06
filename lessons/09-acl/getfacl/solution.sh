getfacl -p "$EX/progetto.txt" 2>/dev/null | sed -n 's/^user:luca:\([rwx-]*\).*/\1/p'
