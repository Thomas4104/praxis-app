/**
 * OMNIA Praxissoftware - KI-Chat Funktionalitaet
 */

document.addEventListener('DOMContentLoaded', function () {
    var chatPanel = document.getElementById('chatPanel');
    var chatToggleBtn = document.getElementById('chatToggleBtn');
    var chatCloseBtn = document.getElementById('chatCloseBtn');
    var chatClearBtn = document.getElementById('chatClearBtn');
    var chatMessages = document.getElementById('chatMessages');
    var chatInput = document.getElementById('chatInput');
    var chatSendBtn = document.getElementById('chatSendBtn');
    var chatTyping = document.getElementById('chatTyping');
    var chatFab = document.getElementById('chatFab');

    if (!chatPanel || !chatInput) return;

    var isOpen = false;
    var isSending = false;

    // === Panel oeffnen/schliessen ===
    function toggleChat() {
        isOpen = !isOpen;
        chatPanel.classList.toggle('open', isOpen);
        document.body.classList.toggle('chat-open', isOpen);

        if (isOpen) {
            chatInput.focus();
            scrollToBottom();
        }
    }

    if (chatToggleBtn) {
        chatToggleBtn.addEventListener('click', toggleChat);
    }

    if (chatCloseBtn) {
        chatCloseBtn.addEventListener('click', function () {
            isOpen = false;
            chatPanel.classList.remove('open');
            document.body.classList.remove('chat-open');
        });
    }

    if (chatFab) {
        chatFab.addEventListener('click', toggleChat);
    }

    // === Nachricht senden ===
    function sendMessage() {
        var message = chatInput.value.trim();
        if (!message || isSending) return;

        // Willkommens-Nachricht entfernen
        var welcome = chatMessages.querySelector('.chat-welcome');
        if (welcome) welcome.remove();

        // Benutzer-Nachricht anzeigen
        addMessage(message, 'user');
        chatInput.value = '';
        chatInput.style.height = 'auto';

        // Senden
        isSending = true;
        chatSendBtn.disabled = true;
        chatTyping.style.display = 'flex';
        scrollToBottom();

        fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        })
            .then(function (response) { return response.json(); })
            .then(function (data) {
                chatTyping.style.display = 'none';
                if (data.error) {
                    addMessage('Fehler: ' + data.error, 'assistant');
                } else {
                    addMessage(data.response, 'assistant', data.timestamp);
                }
            })
            .catch(function () {
                chatTyping.style.display = 'none';
                addMessage('Verbindungsfehler. Bitte versuchen Sie es erneut.', 'assistant');
            })
            .finally(function () {
                isSending = false;
                chatSendBtn.disabled = false;
                scrollToBottom();
            });
    }

    if (chatSendBtn) {
        chatSendBtn.addEventListener('click', sendMessage);
    }

    // Enter zum Senden, Shift+Enter fuer neue Zeile
    chatInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-Resize Chat-Input
    chatInput.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });

    // === Nachricht zum Chat hinzufuegen ===
    function addMessage(content, role, timestamp) {
        var div = document.createElement('div');
        div.className = 'chat-message chat-message-' + role;

        if (role === 'assistant') {
            div.innerHTML = formatMarkdown(content);
        } else {
            div.textContent = content;
        }

        if (timestamp) {
            var timeSpan = document.createElement('span');
            timeSpan.className = 'chat-message-time';
            timeSpan.textContent = timestamp;
            div.appendChild(timeSpan);
        }

        chatMessages.appendChild(div);
        scrollToBottom();
    }

    // === Einfache Markdown-Formatierung ===
    function formatMarkdown(text) {
        if (!text) return '';

        // HTML-Entities escapen
        var html = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');

        // Fett: **text**
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

        // Kursiv: *text*
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

        // Code: `text`
        html = html.replace(/`(.+?)`/g, '<code>$1</code>');

        // Ungeordnete Listen
        html = html.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

        // Geordnete Listen
        html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

        // Zeilenumbrueche
        html = html.replace(/\n/g, '<br>');

        // Doppelte <br> durch Absaetze ersetzen
        html = html.replace(/<br><br>/g, '</p><p>');

        return html;
    }

    // === Auto-Scroll ===
    function scrollToBottom() {
        setTimeout(function () {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }, 50);
    }

    // === Chat leeren ===
    if (chatClearBtn) {
        chatClearBtn.addEventListener('click', function () {
            fetch('/api/chat/clear', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
                .then(function () {
                    chatMessages.innerHTML =
                        '<div class="chat-welcome">' +
                        '<p>Wie kann ich Ihnen helfen?</p>' +
                        '</div>';
                })
                .catch(function () {
                    if (typeof showToast === 'function') {
                        showToast('Fehler beim Leeren des Chats.', 'error');
                    }
                });
        });
    }

    // === Chat-Verlauf laden ===
    function loadHistory() {
        fetch('/api/chat/history')
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (data.messages && data.messages.length > 0) {
                    var welcome = chatMessages.querySelector('.chat-welcome');
                    if (welcome) welcome.remove();

                    data.messages.forEach(function (msg) {
                        addMessage(msg.content, msg.role, msg.timestamp);
                    });
                }
            })
            .catch(function () {
                // Verlauf konnte nicht geladen werden - kein Problem
            });
    }

    loadHistory();
});
