# Avviata da root, l'app ha ricreato il file di stato come root:root 644.
rm -f /srv/app/data/last-start
/srv/app/run.sh > /dev/null
