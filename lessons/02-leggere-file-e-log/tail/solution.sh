tail -n 5 "$EX/app.log" | head -n 1 | sed 's/.*id=//'
