Du bist ein Security QA Engineer. Validiere Phase 6 (Infrastruktur) in /Users/thomasbalke/praxis-app.

1. docker-compose.yml:
   - Keine hardcoded Passwörter (suche nach "omnia_secret")?
   - DB und Redis Ports nicht exponiert oder nur auf 127.0.0.1?
   - Netzwerk-Segmentierung vorhanden?
   - Health-Checks definiert?

2. nginx.conf:
   - HTTPS/TLS konfiguriert?
   - HTTP -> HTTPS Redirect?
   - server_tokens off?
   - Rate-Limiting Zone vorhanden?

3. Dockerfile:
   - Non-root USER Direktive vorhanden?
   - HEALTHCHECK vorhanden?

4. backup.sh:
   - Verschluesselung mit openssl?
   - Checksum-Verifizierung?
   - Retention konfiguriert?

5. requirements.txt:
   - cryptography vorhanden?
   - pyotp vorhanden?

6. .env.example:
   - Alle benoetigten Variablen dokumentiert?
   - ENCRYPTION_KEY, AUDIT_HMAC_KEY, BACKUP_ENCRYPTION_KEY?

Zusammenfassung.
