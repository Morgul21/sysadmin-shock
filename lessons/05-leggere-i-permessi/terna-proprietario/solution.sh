find "$EX" -maxdepth 1 -type f ! -perm -u+x -printf '%f\n'
