Du bist ein Security QA Engineer. Validiere Phase 7 (Tests) in /Users/thomasbalke/praxis-app.

Pruefe ob diese Dateien existieren und syntaktisch korrekt sind:

1. /Users/thomasbalke/praxis-app/tests/__init__.py
2. /Users/thomasbalke/praxis-app/tests/conftest.py
3. /Users/thomasbalke/praxis-app/tests/test_auth.py
4. /Users/thomasbalke/praxis-app/tests/test_rbac.py
5. /Users/thomasbalke/praxis-app/tests/test_encryption.py
6. /Users/thomasbalke/praxis-app/tests/test_audit.py
7. /Users/thomasbalke/praxis-app/tests/test_ai_security.py
8. /Users/thomasbalke/praxis-app/tests/test_billing_integrity.py
9. /Users/thomasbalke/praxis-app/tests/test_multi_tenancy.py
10. /Users/thomasbalke/praxis-app/tests/test_portal_security.py
11. /Users/thomasbalke/praxis-app/tests/test_health.py
12. /Users/thomasbalke/praxis-app/tests/test_soap_versioning.py

Fuer jede Datei:
- Existiert sie?
- Ist die Syntax korrekt? (python3 -c "import ast; ast.parse(open('DATEI').read())")
- Wie viele Test-Klassen/Methoden hat sie?

Zusammenfassung mit Gesamtanzahl Tests.
