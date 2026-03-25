"""Tests fuer Billing-Integritaet und Datensicherheit."""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from tests.conftest import login


class TestInvoiceImmutability:
    """Versendete Rechnungen duerfen nicht geaendert werden."""

    def _create_sent_invoice(self, db, org):
        """Hilfsfunktion: Erstellt eine versendete Rechnung."""
        from models import Invoice, Patient
        from datetime import datetime

        patient = Patient(
            organization_id=org.id,
            first_name='Test',
            last_name='Patient',
            date_of_birth=date(1990, 1, 1),
        )
        db.session.add(patient)
        db.session.flush()

        invoice = Invoice(
            organization_id=org.id,
            patient_id=patient.id,
            invoice_number='RE-2026-0001',
            amount_total=150.00,
            amount_paid=0.00,
            amount_open=150.00,
            status='sent',
            billing_type='KVG',
            billing_model='tiers_garant',
            due_date=date.today() + timedelta(days=30),
            sent_at=datetime.utcnow(),
        )
        db.session.add(invoice)
        db.session.commit()
        return invoice, patient

    def test_sent_invoice_cannot_be_changed_via_route(self, client, admin_user, db, org):
        """Versendete Rechnungen koennen nicht auf draft zurueckgesetzt werden."""
        invoice, _ = self._create_sent_invoice(db, org)
        login(client, 'admin_test', 'SecurePass123!')

        # Versuche Status-Aenderung ueber edit-Route (falls vorhanden)
        resp = client.post(f'/billing/{invoice.id}/edit', data={
            'status': 'draft',
            'amount_total': '200.00',
        }, follow_redirects=True)

        # Rechnung muss weiterhin 'sent' sein
        with client.application.app_context():
            from models import Invoice
            inv = db.session.get(Invoice, invoice.id)
            assert inv.status == 'sent'

    def test_cancelled_invoice_cannot_be_reactivated(self, client, admin_user, db, org):
        """Stornierte Rechnungen koennen nicht reaktiviert werden."""
        from models import Invoice, Patient
        patient = Patient(
            organization_id=org.id,
            first_name='Test',
            last_name='Storno',
            date_of_birth=date(1990, 1, 1),
        )
        db.session.add(patient)
        db.session.flush()

        invoice = Invoice(
            organization_id=org.id,
            patient_id=patient.id,
            invoice_number='RE-2026-0010',
            amount_total=100.00,
            amount_paid=0.00,
            amount_open=100.00,
            status='cancelled',
            billing_type='KVG',
            billing_model='tiers_garant',
            due_date=date.today() + timedelta(days=30),
        )
        db.session.add(invoice)
        db.session.commit()

        login(client, 'admin_test', 'SecurePass123!')

        # Versuch die Rechnung zu senden
        resp = client.post(f'/billing/{invoice.id}/send', follow_redirects=True)

        with client.application.app_context():
            inv = db.session.get(Invoice, invoice.id)
            assert inv.status == 'cancelled', 'Stornierte Rechnung darf nicht reaktiviert werden'


class TestPaymentValidation:
    """Zahlungsvalidierung im billing_service."""

    def _create_invoice_for_payment(self, db, org, amount=100.00):
        """Erstellt eine Rechnung im Status 'sent' fuer Zahlungstests."""
        from models import Invoice, Patient
        from datetime import datetime

        patient = Patient(
            organization_id=org.id,
            first_name='Zahlung',
            last_name='Test',
            date_of_birth=date(1985, 5, 15),
        )
        db.session.add(patient)
        db.session.flush()

        invoice = Invoice(
            organization_id=org.id,
            patient_id=patient.id,
            invoice_number=f'RE-2026-{patient.id:04d}',
            amount_total=amount,
            amount_paid=0.00,
            amount_open=amount,
            status='sent',
            billing_type='KVG',
            billing_model='tiers_garant',
            due_date=date.today() + timedelta(days=30),
            sent_at=datetime.utcnow(),
        )
        db.session.add(invoice)
        db.session.commit()
        return invoice

    def test_payment_cannot_exceed_open_amount(self, app, db, org):
        """Zahlung darf offenen Betrag nicht uebersteigen."""
        from services.billing_service import record_payment
        with app.app_context():
            invoice = self._create_invoice_for_payment(db, org, amount=100.00)

            payment, error = record_payment(
                invoice.id,
                amount=200.00,
                payment_date=date.today(),
                payment_method='bank_transfer',
            )
            assert payment is None
            assert error is not None
            assert 'uebersteigt' in error

    def test_payment_amount_must_be_positive(self, app, db, org):
        """Zahlungsbetrag muss positiv sein."""
        from services.billing_service import record_payment
        with app.app_context():
            invoice = self._create_invoice_for_payment(db, org, amount=100.00)

            # Negativer Betrag
            payment, error = record_payment(
                invoice.id,
                amount=-50.00,
                payment_date=date.today(),
                payment_method='bank_transfer',
            )
            assert payment is None
            assert 'groesser als 0' in error

            # Null-Betrag
            payment, error = record_payment(
                invoice.id,
                amount=0,
                payment_date=date.today(),
                payment_method='bank_transfer',
            )
            assert payment is None
            assert error is not None

    def test_payment_on_draft_invoice_rejected(self, app, db, org):
        """Zahlung auf Entwurf-Rechnung wird abgelehnt."""
        from services.billing_service import record_payment
        from models import Invoice, Patient
        with app.app_context():
            patient = Patient(
                organization_id=org.id,
                first_name='Draft',
                last_name='Test',
                date_of_birth=date(1990, 1, 1),
            )
            db.session.add(patient)
            db.session.flush()

            invoice = Invoice(
                organization_id=org.id,
                patient_id=patient.id,
                invoice_number='RE-2026-DRAFT',
                amount_total=100.00,
                amount_paid=0.00,
                amount_open=100.00,
                status='draft',
                billing_type='KVG',
                due_date=date.today() + timedelta(days=30),
            )
            db.session.add(invoice)
            db.session.commit()

            payment, error = record_payment(
                invoice.id,
                amount=50.00,
                payment_date=date.today(),
                payment_method='bank_transfer',
            )
            assert payment is None
            assert 'Status' in error

    def test_payment_on_cancelled_invoice_rejected(self, app, db, org):
        """Zahlung auf stornierte Rechnung wird abgelehnt."""
        from services.billing_service import record_payment
        from models import Invoice, Patient
        with app.app_context():
            patient = Patient(
                organization_id=org.id,
                first_name='Cancel',
                last_name='Test',
                date_of_birth=date(1990, 1, 1),
            )
            db.session.add(patient)
            db.session.flush()

            invoice = Invoice(
                organization_id=org.id,
                patient_id=patient.id,
                invoice_number='RE-2026-CANCEL',
                amount_total=100.00,
                amount_paid=0.00,
                amount_open=100.00,
                status='cancelled',
                billing_type='KVG',
                due_date=date.today() + timedelta(days=30),
            )
            db.session.add(invoice)
            db.session.commit()

            payment, error = record_payment(
                invoice.id,
                amount=50.00,
                payment_date=date.today(),
                payment_method='bank_transfer',
            )
            assert payment is None
            assert error is not None

    def test_partial_payment_updates_status(self, app, db, org):
        """Teilzahlung setzt Status auf partially_paid."""
        from services.billing_service import record_payment
        from models import Invoice
        with app.app_context():
            invoice = self._create_invoice_for_payment(db, org, amount=100.00)

            payment, error = record_payment(
                invoice.id,
                amount=50.00,
                payment_date=date.today(),
                payment_method='bank_transfer',
            )
            assert payment is not None
            assert error is None

            inv = db.session.get(Invoice, invoice.id)
            assert inv.status == 'partially_paid'
            assert float(inv.amount_open) == 50.00

    def test_full_payment_sets_paid(self, app, db, org):
        """Vollstaendige Zahlung setzt Status auf paid."""
        from services.billing_service import record_payment
        from models import Invoice
        with app.app_context():
            invoice = self._create_invoice_for_payment(db, org, amount=100.00)

            payment, error = record_payment(
                invoice.id,
                amount=100.00,
                payment_date=date.today(),
                payment_method='bank_transfer',
            )
            assert payment is not None

            inv = db.session.get(Invoice, invoice.id)
            assert inv.status == 'paid'
            assert float(inv.amount_open) == 0.00

    def test_future_payment_date_rejected(self, app, db, org):
        """Zahlungsdatum in der Zukunft wird abgelehnt."""
        from services.billing_service import record_payment
        with app.app_context():
            invoice = self._create_invoice_for_payment(db, org, amount=100.00)

            payment, error = record_payment(
                invoice.id,
                amount=50.00,
                payment_date=date.today() + timedelta(days=7),
                payment_method='bank_transfer',
            )
            assert payment is None
            assert 'Zukunft' in error


class TestInvoiceNumberUniqueness:
    """Rechnungsnummern muessen pro Organisation eindeutig sein."""

    def test_duplicate_invoice_number_same_org_fails(self, app, db, org):
        """Doppelte Rechnungsnummer in gleicher Organisation schlaegt fehl."""
        from models import Invoice, Patient
        from sqlalchemy.exc import IntegrityError
        with app.app_context():
            patient = Patient(
                organization_id=org.id,
                first_name='Unique',
                last_name='Test',
                date_of_birth=date(1990, 1, 1),
            )
            db.session.add(patient)
            db.session.flush()

            inv1 = Invoice(
                organization_id=org.id,
                patient_id=patient.id,
                invoice_number='RE-2026-DUP',
                amount_total=100.00,
                amount_open=100.00,
                status='draft',
            )
            db.session.add(inv1)
            db.session.commit()

            inv2 = Invoice(
                organization_id=org.id,
                patient_id=patient.id,
                invoice_number='RE-2026-DUP',
                amount_total=200.00,
                amount_open=200.00,
                status='draft',
            )
            db.session.add(inv2)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_same_invoice_number_different_org_ok(self, app, db, org, other_org):
        """Gleiche Rechnungsnummer in verschiedenen Organisationen ist erlaubt."""
        from models import Invoice, Patient
        with app.app_context():
            p1 = Patient(organization_id=org.id, first_name='A', last_name='B',
                         date_of_birth=date(1990, 1, 1))
            p2 = Patient(organization_id=other_org.id, first_name='C', last_name='D',
                         date_of_birth=date(1990, 1, 1))
            db.session.add_all([p1, p2])
            db.session.flush()

            inv1 = Invoice(
                organization_id=org.id, patient_id=p1.id,
                invoice_number='RE-2026-CROSS', amount_total=100.00,
                amount_open=100.00, status='draft',
            )
            inv2 = Invoice(
                organization_id=other_org.id, patient_id=p2.id,
                invoice_number='RE-2026-CROSS', amount_total=200.00,
                amount_open=200.00, status='draft',
            )
            db.session.add_all([inv1, inv2])
            db.session.commit()  # Darf keinen Fehler werfen

            assert inv1.id is not None
            assert inv2.id is not None

    def test_generate_invoice_number_sequential(self, app, db, org):
        """generate_invoice_number erzeugt aufeinanderfolgende Nummern."""
        from services.billing_service import generate_invoice_number
        with app.app_context():
            nr1 = generate_invoice_number(org.id)
            nr2 = generate_invoice_number(org.id)
            db.session.commit()

            assert nr1 != nr2
            # Beide muessen das aktuelle Jahr enthalten
            year = str(date.today().year)
            assert year in nr1
            assert year in nr2
