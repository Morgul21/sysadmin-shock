# luca è nel gruppo, che può scrivere; una voce dell'ACL solo per lui gli toglie tutto.
# La voce di anna deve restare: setfacl -b (togliere tutta l'ACL) non va bene.
groupadd tecnici
useradd -M -N -G tecnici luca
useradd -M -N anna
mkdir -p "$EX"
chmod 755 "$EX"
echo "registro di prova" > "$EX/registro.log"
chown root:tecnici "$EX/registro.log"
chmod 664 "$EX/registro.log"
setfacl -m u:luca:-,u:anna:rw "$EX/registro.log"
