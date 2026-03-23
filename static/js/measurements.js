/**
 * Messwert-Verlaufsgrafik mit Canvas API
 * Einfache Liniendiagramme ohne externe Libraries
 */

function drawMeasurementChart(canvas, labels, values, config) {
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;

    // Responsiv: Canvas-Groesse an Container anpassen
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 300 * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = '300px';
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = 300;

    // Zeichenbereich mit Rand
    const padding = { top: 30, right: 30, bottom: 50, left: 50 };
    const chartW = W - padding.left - padding.right;
    const chartH = H - padding.top - padding.bottom;

    // Hintergrund
    ctx.clearRect(0, 0, W, H);

    // Skala
    const minVal = config.min !== undefined ? config.min : Math.min(...values) - 1;
    const maxVal = config.max !== undefined ? config.max : Math.max(...values) + 1;
    const range = maxVal - minVal || 1;

    // Hilfsfunktionen
    function xPos(i) {
        if (values.length === 1) return padding.left + chartW / 2;
        return padding.left + (i / (values.length - 1)) * chartW;
    }
    function yPos(val) {
        return padding.top + chartH - ((val - minVal) / range) * chartH;
    }

    // Gitterlinien und Y-Achsen-Beschriftung
    ctx.strokeStyle = '#e8e8e8';
    ctx.lineWidth = 1;
    ctx.fillStyle = '#888';
    ctx.font = '11px system-ui, -apple-system, sans-serif';
    ctx.textAlign = 'right';

    const numGridLines = 5;
    for (let i = 0; i <= numGridLines; i++) {
        const val = minVal + (range / numGridLines) * i;
        const y = yPos(val);

        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(W - padding.right, y);
        ctx.stroke();

        ctx.fillText(Math.round(val * 10) / 10, padding.left - 8, y + 4);
    }

    // X-Achsen-Beschriftung
    ctx.textAlign = 'center';
    ctx.fillStyle = '#666';
    labels.forEach(function(label, i) {
        const x = xPos(i);
        // Bei vielen Labels nur jedes n-te anzeigen
        if (labels.length <= 10 || i % Math.ceil(labels.length / 10) === 0 || i === labels.length - 1) {
            ctx.save();
            ctx.translate(x, H - padding.bottom + 15);
            ctx.rotate(-Math.PI / 6);
            ctx.fillText(label, 0, 0);
            ctx.restore();
        }
    });

    // Linie zeichnen
    if (values.length > 1) {
        // Flaeche unter der Linie (halbtransparent)
        ctx.beginPath();
        ctx.moveTo(xPos(0), yPos(values[0]));
        for (let i = 1; i < values.length; i++) {
            ctx.lineTo(xPos(i), yPos(values[i]));
        }
        ctx.lineTo(xPos(values.length - 1), padding.top + chartH);
        ctx.lineTo(xPos(0), padding.top + chartH);
        ctx.closePath();
        ctx.fillStyle = hexToRgba(config.color || '#4a90d9', 0.1);
        ctx.fill();

        // Linie
        ctx.beginPath();
        ctx.moveTo(xPos(0), yPos(values[0]));
        for (let i = 1; i < values.length; i++) {
            ctx.lineTo(xPos(i), yPos(values[i]));
        }
        ctx.strokeStyle = config.color || '#4a90d9';
        ctx.lineWidth = 2.5;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.stroke();
    }

    // Datenpunkte
    values.forEach(function(val, i) {
        const x = xPos(i);
        const y = yPos(val);

        // Weisser Kreis-Hintergrund
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#fff';
        ctx.fill();
        ctx.strokeStyle = config.color || '#4a90d9';
        ctx.lineWidth = 2.5;
        ctx.stroke();
    });

    // Titel
    ctx.fillStyle = '#333';
    ctx.font = 'bold 13px system-ui, -apple-system, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(config.label || 'Messwerte', padding.left, 18);

    // Hover-Tooltip Setup
    setupChartTooltip(canvas, values, labels, config, xPos, yPos, padding);
}

function setupChartTooltip(canvas, values, labels, config, xPos, yPos, padding) {
    // Bestehende Listener entfernen
    const newCanvas = canvas.cloneNode(true);
    canvas.parentNode.replaceChild(newCanvas, canvas);

    // Canvas-ID beibehalten
    newCanvas.id = canvas.id;

    // Tooltip-Element erstellen/finden
    let tooltip = newCanvas.parentElement.querySelector('.chart-tooltip');
    if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.className = 'chart-tooltip';
        tooltip.style.cssText = 'position:absolute;display:none;background:#333;color:#fff;padding:6px 10px;border-radius:6px;font-size:12px;pointer-events:none;z-index:10;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,0.2)';
        newCanvas.parentElement.style.position = 'relative';
        newCanvas.parentElement.appendChild(tooltip);
    }

    newCanvas.addEventListener('mousemove', function(e) {
        const rect = newCanvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;

        // Naechsten Datenpunkt finden
        let closestIdx = -1;
        let closestDist = Infinity;

        values.forEach(function(val, i) {
            const px = xPos(i);
            const py = yPos(val);
            const dist = Math.sqrt(Math.pow(mouseX - px, 2) + Math.pow(mouseY - py, 2));
            if (dist < closestDist && dist < 30) {
                closestDist = dist;
                closestIdx = i;
            }
        });

        if (closestIdx >= 0) {
            tooltip.innerHTML = '<strong>' + labels[closestIdx] + '</strong><br>' +
                               (config.label || 'Wert') + ': ' + values[closestIdx];
            tooltip.style.display = 'block';
            tooltip.style.left = (xPos(closestIdx) - tooltip.offsetWidth / 2) + 'px';
            tooltip.style.top = (yPos(values[closestIdx]) - tooltip.offsetHeight - 10) + 'px';
        } else {
            tooltip.style.display = 'none';
        }
    });

    newCanvas.addEventListener('mouseleave', function() {
        tooltip.style.display = 'none';
    });
}

function hexToRgba(hex, alpha) {
    hex = hex.replace('#', '');
    const r = parseInt(hex.substring(0, 2), 16);
    const g = parseInt(hex.substring(2, 4), 16);
    const b = parseInt(hex.substring(4, 6), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
}
