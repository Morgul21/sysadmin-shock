from __future__ import annotations

import unittest

from breakfix.guardrail import check_command


BLOCKED = {
    # correzioni eccessive
    "chmod 777 /srv/app/run.sh": "scrivibile-da-tutti",
    "chmod 0666 /srv/app/config": "scrivibile-da-tutti",
    "chmod a+rwx /srv/app/run.sh": "scrivibile-da-tutti",
    "chmod u+x,o+w /srv/app/run.sh": "scrivibile-da-tutti",
    "sudo /bin/chmod 777 /srv/app/run.sh": "scrivibile-da-tutti",
    "ls -l /srv/app && chmod 777 /srv/app/run.sh": "scrivibile-da-tutti",
    "chmod 4755 /srv/app/run.sh": "setuid",
    "chmod u+s /usr/bin/find": "setuid",
    # operazioni ricorsive su directory di sistema
    "chmod -R 777 /srv": "ricorsivo-di-sistema",
    "chown -R app:app /": "ricorsivo-di-sistema",
    "rm -rf /srv/app/*": "ricorsivo-di-sistema",
    "rm -fr /etc/": "ricorsivo-di-sistema",
    "rm -rf --no-preserve-root /": "ricorsivo-di-sistema",
    # distruggono la sandbox invece di ripararla
    "kill -9 1": "distruzione-sandbox",
    "kill -- -1": "distruzione-sandbox",
    "pkill sleep": "distruzione-sandbox",
    "reboot": "distruzione-sandbox",
    "dd if=/dev/zero of=/dev/sda": "distruzione-sandbox",
    ":(){ :|:& };:": "fork-bomb",
    # comandi costruiti a runtime: la denylist non li vedrebbe
    "eval \"$(echo Y2htb2QgNzc3IC9zcnY= | base64 -d)\"": "comando-dinamico",
    "echo 'chmod 777 /srv' | sh": "comando-dinamico",
    "bash -c 'chmod 777 /srv'": "comando-dinamico",
    "python3 -c 'import os; os.chmod(\"/srv\", 0o777)'": "comando-dinamico",
    # file di autenticazione
    "echo 'app ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers": "file-di-autenticazione",
    "sed -i 's/^app:x/app:/' /etc/passwd": "file-di-autenticazione",
}

# Diagnosi e fix legittimi: il guardrail non deve impedire di riparare.
ALLOWED = [
    "ls -l /srv/app",
    "id app",
    "stat -c '%a %U:%G' /srv/app/run.sh",
    "cat /var/log/app/app.log",
    "free -m",
    "ps aux --sort=-%mem | head -5",
    "cat /proc/meminfo",
    "chmod 755 /srv/app/run.sh",
    "chmod u+x /srv/app/run.sh",
    "chmod +w /srv/app/notes.txt",
    "chmod 1777 /tmp",
    "chown app:app /srv/app/run.sh",
    "chown -R app:app /srv/app/data",
    "usermod -aG adm app",
    "kill -9 4242",
    "kill $(pgrep -f memhog)",
    "rm -rf /tmp/cache",
    "cat /etc/passwd",
    "runuser -u app -- /srv/app/run.sh",
    "su app -c /srv/app/run.sh",
]


class GuardrailTest(unittest.TestCase):
    def test_blocks_forbidden_commands(self) -> None:
        for command, rule in BLOCKED.items():
            with self.subTest(command=command):
                blocked = check_command(command)
                self.assertIsNotNone(blocked, "doveva essere bloccato")
                self.assertEqual(blocked.rule, rule)

    def test_allows_diagnosis_and_targeted_fixes(self) -> None:
        for command in ALLOWED:
            with self.subTest(command=command):
                self.assertIsNone(check_command(command))


if __name__ == "__main__":
    unittest.main()
