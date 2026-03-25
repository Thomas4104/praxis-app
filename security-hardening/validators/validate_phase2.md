Du bist ein Security QA Engineer. Validiere die Phase-2 Aenderungen (Verschluesselung) in /Users/thomasbalke/praxis-app.

1. /Users/thomasbalke/praxis-app/utils/encryption.py
   - Existiert die Datei?
   - Gibt es encrypt_value(), decrypt_value(), EncryptedString?
   - Syntax korrekt?

2. /Users/thomasbalke/praxis-app/models.py
   - Wird EncryptedString importiert?
   - Sind ahv_number, insurance_number, iban, qr_iban, SOAP-Felder, Diagnose-Felder auf EncryptedString umgestellt?
   - Syntax korrekt?

3. /Users/thomasbalke/praxis-app/requirements.txt
   - Ist cryptography als Dependency vorhanden?

4. /Users/thomasbalke/praxis-app/scripts/encrypt_existing_data.py
   - Existiert das Script?
   - Syntax korrekt?

Fasse zusammen: Was ist OK, was fehlt.
