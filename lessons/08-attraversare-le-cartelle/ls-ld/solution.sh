for d in alfa beta gamma; do
    if runuser -u app -- test -x "$EX/$d" && ! runuser -u app -- test -r "$EX/$d"; then echo "$d"; fi
done
