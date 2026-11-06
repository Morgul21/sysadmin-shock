# Tre lavori: uno a caso occupa molta più memoria degli altri due.
set -- $(shuf -e report esporta indicizza)
job "$1" "$(rnd 40 60)"
job "$2" "$(rnd 5 15)"
job "$3" "$(rnd 5 15)"
