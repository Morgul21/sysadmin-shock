baseline
# chown app:app sul log aggira la ACL (il proprietario usa user::, non user:app:) ma la lascia lì,
# e dà all'app il potere di cancellare o riscrivere il proprio log. La causa va rimossa.
owner=$(stat -c '%U:%G' /var/log/app/app.log)
[ "$owner" = "root:app" ] || fail "il log ora è di $owner: deve restare root:app, la causa è un'altra"
pass "l'app scrive di nuovo nel log"
