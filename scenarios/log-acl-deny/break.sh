# La entry per l'utente app vince su quella del gruppo app: sola lettura.
setfacl -m u:app:r /var/log/app/app.log
