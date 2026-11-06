for f in "$EX"/*; do
    [ -n "$(getfacl --skip-base -p "$f" 2>/dev/null)" ] && echo "${f##*/}"
done
true
