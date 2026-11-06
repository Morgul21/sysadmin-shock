if runuser -u app -- test -r "$EX/nota.txt"; then echo si; else echo no; fi
