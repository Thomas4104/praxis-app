// OMNIA Praxissoftware - Globale Funktionen

// Sidebar ein-/ausblenden (Mobile)
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');
    sidebar.classList.toggle('open');
    overlay.classList.toggle('active');
}

// KI-Chat-Panel ein-/ausblenden
function toggleChat() {
    const chatPanel = document.getElementById('chatPanel');
    const mainContent = document.getElementById('mainContent');
    const overlay = document.getElementById('overlay');

    chatPanel.classList.toggle('open');

    // Desktop: Hauptinhalt anpassen
    if (window.innerWidth > 768) {
        mainContent.classList.toggle('chat-open');
    } else {
        overlay.classList.toggle('active');
    }

    // Beim ersten Öffnen: Chat-Verlauf laden
    if (chatPanel.classList.contains('open') && !chatPanel.dataset.loaded) {
        loadChatHistory();
        chatPanel.dataset.loaded = 'true';
    }

    // Fokus auf Eingabefeld
    if (chatPanel.classList.contains('open')) {
        setTimeout(() => document.getElementById('chatInput').focus(), 300);
    }
}

// Alle Panels schliessen
function closePanels() {
    const sidebar = document.getElementById('sidebar');
    const chatPanel = document.getElementById('chatPanel');
    const mainContent = document.getElementById('mainContent');
    const overlay = document.getElementById('overlay');

    sidebar.classList.remove('open');
    chatPanel.classList.remove('open');
    mainContent.classList.remove('chat-open');
    overlay.classList.remove('active');
}

// Flash-Messages nach 5 Sekunden automatisch ausblenden
document.addEventListener('DOMContentLoaded', () => {
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(msg => {
        setTimeout(() => {
            msg.style.opacity = '0';
            msg.style.transition = 'opacity 0.3s';
            setTimeout(() => msg.remove(), 300);
        }, 5000);
    });
});
