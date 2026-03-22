// OMNIA Praxissoftware - KI-Chat Logik

// Chat-Verlauf laden
async function loadChatHistory() {
    try {
        const response = await fetch('/api/chat/history');
        const data = await response.json();

        if (data.messages && data.messages.length > 0) {
            const container = document.getElementById('chatMessages');
            // Willkommensnachricht entfernen wenn Verlauf existiert
            const welcome = container.querySelector('.chat-welcome');
            if (welcome) welcome.remove();

            data.messages.forEach(msg => {
                addMessageToUI(msg.role, msg.content);
            });
            scrollToBottom();
        }
    } catch (error) {
        console.error('Chat-Verlauf laden fehlgeschlagen:', error);
    }
}

// Nachricht senden
async function sendMessage(event) {
    event.preventDefault();

    const input = document.getElementById('chatInput');
    const sendBtn = document.getElementById('chatSendBtn');
    const message = input.value.trim();

    if (!message) return;

    // UI aktualisieren
    input.value = '';
    input.style.height = 'auto';
    sendBtn.disabled = true;

    // Willkommensnachricht entfernen
    const welcome = document.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    // Benutzer-Nachricht anzeigen
    addMessageToUI('user', message);

    // Lade-Indikator
    const loadingMsg = addMessageToUI('loading', 'Denke nach...');
    scrollToBottom();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message }),
        });

        const data = await response.json();

        // Lade-Indikator entfernen
        if (loadingMsg) loadingMsg.remove();

        if (data.error) {
            addMessageToUI('assistant', 'Fehler: ' + data.error);
        } else {
            addMessageToUI('assistant', data.response);
        }
    } catch (error) {
        if (loadingMsg) loadingMsg.remove();
        addMessageToUI('assistant', 'Verbindungsfehler. Bitte versuche es erneut.');
    }

    sendBtn.disabled = false;
    scrollToBottom();
    input.focus();
}

// Nachricht zur UI hinzufügen
function addMessageToUI(role, content) {
    const container = document.getElementById('chatMessages');
    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-message ${role}`;
    msgDiv.textContent = content;
    container.appendChild(msgDiv);
    return msgDiv;
}

// Zum Ende scrollen
function scrollToBottom() {
    const container = document.getElementById('chatMessages');
    container.scrollTop = container.scrollHeight;
}

// Enter zum Senden, Shift+Enter für neue Zeile
function handleChatKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        document.getElementById('chatForm').dispatchEvent(new Event('submit'));
    }
}

// Textarea automatisch vergrössern
function autoResizeTextarea(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

// Chat leeren
async function clearChat() {
    try {
        await fetch('/api/chat/clear', { method: 'POST' });
        const container = document.getElementById('chatMessages');
        container.innerHTML = `
            <div class="chat-welcome">
                <p><strong>Chat wurde geleert.</strong></p>
                <p>Was kann ich für dich tun?</p>
            </div>
        `;
    } catch (error) {
        console.error('Chat leeren fehlgeschlagen:', error);
    }
}
