# Dashboard-Routen: Startseite, KI-Chat-API

import json
from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from blueprints.dashboard import dashboard_bp
from models import db, ChatMessage, Appointment, Patient, Invoice
from ai.coordinator import process_chat_message
from datetime import datetime, date, time


@dashboard_bp.route('/')
@login_required
def index():
    # Heutige Termine zählen
    today_start = datetime.combine(date.today(), time.min)
    today_end = datetime.combine(date.today(), time.max)
    termine_heute = Appointment.query.filter(
        Appointment.start_time >= today_start,
        Appointment.start_time <= today_end,
        Appointment.status != 'cancelled'
    ).count()

    patienten_total = Patient.query.filter_by(is_active=True).count()

    # Abrechnungs-Statistiken
    rechnungen_offen = Invoice.query.filter(
        Invoice.status.in_(['open', 'sent', 'answered', 'partially_paid'])
    ).count()
    rechnungen_ueberfaellig = Invoice.query.filter(
        Invoice.status.in_(['open', 'sent', 'answered', 'partially_paid']),
        Invoice.due_date < date.today()
    ).count()

    return render_template('dashboard/index.html',
                           termine_heute=termine_heute,
                           patienten_total=patienten_total,
                           rechnungen_offen=rechnungen_offen,
                           rechnungen_ueberfaellig=rechnungen_ueberfaellig)


@dashboard_bp.route('/api/chat', methods=['POST'])
@login_required
def chat():
    """API-Endpoint für den KI-Chat."""
    data = request.get_json()
    user_message = data.get('message', '').strip()

    if not user_message:
        return jsonify({'error': 'Keine Nachricht'}), 400

    # Chat-Verlauf laden (letzte 20 Nachrichten)
    history_records = ChatMessage.query.filter_by(user_id=current_user.id).order_by(
        ChatMessage.created_at.desc()
    ).limit(20).all()
    history_records.reverse()

    conversation_history = []
    for msg in history_records:
        conversation_history.append({
            'role': msg.role,
            'content': msg.content,
        })

    # Benutzer-Nachricht speichern
    user_msg = ChatMessage(
        user_id=current_user.id,
        role='user',
        content=user_message,
    )
    db.session.add(user_msg)
    db.session.commit()

    # KI-Antwort generieren
    try:
        response = process_chat_message(user_message, conversation_history)
    except Exception as e:
        response = f'Es ist ein Fehler aufgetreten: {str(e)}'

    # Antwort speichern
    assistant_msg = ChatMessage(
        user_id=current_user.id,
        role='assistant',
        content=response,
    )
    db.session.add(assistant_msg)
    db.session.commit()

    return jsonify({'response': response})


@dashboard_bp.route('/api/chat/history')
@login_required
def chat_history():
    """Gibt den Chat-Verlauf zurück."""
    messages = ChatMessage.query.filter_by(user_id=current_user.id).order_by(
        ChatMessage.created_at.desc()
    ).limit(50).all()
    messages.reverse()

    return jsonify({
        'messages': [{
            'role': msg.role,
            'content': msg.content,
            'timestamp': msg.created_at.strftime('%H:%M'),
        } for msg in messages]
    })


@dashboard_bp.route('/api/chat/clear', methods=['POST'])
@login_required
def chat_clear():
    """Löscht den Chat-Verlauf."""
    ChatMessage.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'message': 'Chat-Verlauf gelöscht'})
