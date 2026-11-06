ps -eo pid=,rss= --sort=-rss | head -1 | awk '{print $1}'
