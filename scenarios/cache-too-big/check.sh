baseline
# Disattivare la cache farebbe partire l'app, ma non è una riparazione.
cache_mb=$(sed -n 's/^CACHE_MB=//p' /srv/app/app.conf)
[ "${cache_mb:-0}" -ge 32 ] || fail "CACHE_MB=$cache_mb: la cache è stata ridotta troppo o disattivata"
pass "la cache sta nel limite di memoria del container"
