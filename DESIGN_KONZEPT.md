# OMNIA Praxissoftware - Designkonzept & Umbauplan

## Expertenteam

**Lena Hartmann** - Lead UX Designerin (12 Jahre Erfahrung, spezialisiert auf Healthcare SaaS)
**Marco Berchtold** - UI Designer & Visual Identity (10 Jahre, ehemals Swisscom Health, Helsana Digital)
**Sarah Kim** - Interaction Designer & Accessibility (8 Jahre, WCAG-Zertifiziert, Fokus auf komplexe Formulare)
**David Brunner** - Frontend-Architekt & Design Systems (15 Jahre, Design Tokens, Component Libraries)
**Nina Vogt** - UX Researcher & Usability Testing (9 Jahre, Healthcare-Workflows, Schweizer Markt)

---

## Teil 1: Ist-Analyse

### 1.1 Aktueller Stand (Score: 75/100)

| Bereich | Score | Bewertung |
|---------|-------|-----------|
| Farbsystem | 8/10 | Gut definiert, aber inkonsistente Nutzung in Submodulen |
| Typografie | 9/10 | Saubere System-Font-Stack, gute Skalierung |
| Spacing | 7/10 | CSS-Variablen vorhanden, aber viele Hardcoded-Werte |
| Komponenten | 6/10 | Grundgerüst da, aber Inkonsistenzen zwischen Modulen |
| Formulare | 5/10 | Verschiedene Klassen (`.form-input` vs `.form-control`), Inline-Styles |
| Responsive | 6/10 | Grundsätzlich vorhanden, Mobile-Experience unvollständig |
| Barrierefreiheit | 5/10 | Fehlende ARIA-Labels, Fokus-Indikatoren, Skip-Links |
| Gesamteindruck | 6/10 | Funktional, aber visuell "2020er-Look", kein modernes Feeling |

### 1.2 Kritische Schwächen (Lena Hartmann, Nina Vogt)

**UX-Probleme:**
- Keine klare visuelle Hierarchie auf Dashboard-Widgets
- Kalender-Interaktionen (Drag & Drop) fehlen haptisches Feedback
- Modaler Workflow für Terminbuchung zu viele Klicks (5+ Schritte)
- Suchfunktion ohne Kontext-Ergebnisse (zeigt alles gleich an)
- Keine Onboarding-Hilfe für neue Nutzer
- `confirm()` Browser-Dialoge statt gestylter Confirmations
- Fehlende Undo-Funktionalität bei kritischen Aktionen

**UI-Probleme (Marco Berchtold):**
- Farbpalette wirkt kalt und generisch (Standard-Bootstrap-Blau `#4a90d9`)
- Keine Markenidentität sichtbar (OMNIA-Branding minimal)
- Sidebar-Icons ohne einheitlichen Stil
- Keine Micro-Interactions oder Feedback-Animationen
- Cards wirken "flach" ohne visuelle Tiefe
- Kein Dark Mode oder Theming-Option
- Status-Badges zu klein und schwer unterscheidbar

**Technische Design-Schulden (David Brunner):**
- `portal.css` definiert eigenes, paralleles Farbsystem
- `calendar.css` referenziert undefinierte `--gray-*` Variablen
- `treatment.css` mischt CSS-Variablen mit Hardcoded-Werten
- Kein einheitliches Komponentensystem (`.table` vs `.data-table`)
- Inline-Styles in Templates (besonders `patients/form.html`)
- Verschiedene Tab-Implementierungen pro Modul
- Keine Design Tokens für systematische Updates

**Accessibility-Mängel (Sarah Kim):**
- Farbkontrast: `#adb5bd` auf Weiss = WCAG AA Fail
- Keine Skip-Links für Keyboard-Navigation
- Icon-Only-Buttons ohne ARIA-Labels (Header-Icons)
- Modals ohne Focus-Trap
- Farbe als einziger Status-Indikator (Prioritäts-Dots)
- Tabellen ohne `scope`-Attribute
- Kein `aria-busy` bei Ladezuständen

### 1.3 Stärken (die wir beibehalten)

- Saubere CSS-Variablen-Architektur als Fundament
- Gute responsive Grundstruktur (Sidebar-Collapse, Grid)
- Konsistente Empty-States (Icon + Text + CTA)
- Durchdachtes Toast-Notification-System
- KI-Chat-Integration im Seitenbereich
- System-Font-Stack (performant, plattformnativ)

---

## Teil 2: Designkonzept "OMNIA 2.0"

### 2.1 Design-Vision (Marco Berchtold)

> "Vertrauenswürdig wie ein Arztgespräch, effizient wie ein Schweizer Uhrwerk,
> modern wie ein Fintech. OMNIA soll sich anfühlen wie ein Premium-Tool,
> das Therapeuten gerne öffnen."

**Design-Prinzipien:**
1. **Clarity First** - Jedes Element hat einen klaren Zweck
2. **Calm Computing** - Reduzierte visuelle Reize, sanfte Übergänge
3. **Progressive Disclosure** - Komplexität erst zeigen, wenn nötig
4. **Accessible by Default** - WCAG 2.1 AA als Minimum-Standard
5. **Swiss Precision** - Saubere Ausrichtung, konsistente Abstände

### 2.2 Neue Farbpalette

```
PRIMÄRFARBEN (Healthcare-Teal statt generisches Blau)
--color-primary-50:  #eef7f7    Hintergründe, Hover-States
--color-primary-100: #d5eded    Badges, Tags
--color-primary-200: #a8d8d8    Borders, Outlines
--color-primary-300: #6bbfbf    Sekundäre Aktionen
--color-primary-400: #3da8a8    Aktive Elemente
--color-primary-500: #1a8f8f    PRIMÄRFARBE (Buttons, Links, Fokus)
--color-primary-600: #157575    Hover-States
--color-primary-700: #105b5b    Pressed-States
--color-primary-800: #0b4242    Text auf hellem Grund
--color-primary-900: #062929    Starker Kontrast

AKZENTFARBE (Warm Coral für CTAs und Highlights)
--color-accent-500:  #E07A5F    Call-to-Actions, wichtige Aktionen
--color-accent-600:  #C96A52    Hover

NEUTRALS (Wärmeres Grau statt Blau-Grau)
--color-neutral-50:  #FAFAF9    Page Background
--color-neutral-100: #F5F5F4    Card Backgrounds, Sidebar
--color-neutral-200: #E7E5E4    Borders, Dividers
--color-neutral-300: #D6D3D1    Input Borders
--color-neutral-400: #A8A29E    Placeholder Text
--color-neutral-500: #78716C    Sekundärer Text
--color-neutral-600: #57534E    Label Text
--color-neutral-700: #44403C    Body Text
--color-neutral-800: #292524    Headings
--color-neutral-900: #1C1917    Starker Text

SEMANTISCHE FARBEN (gedämpfter, professioneller)
--color-success:     #059669    Abgeschlossen, Bestätigt
--color-success-bg:  #ECFDF5
--color-warning:     #D97706    Warnung, Ausstehend
--color-warning-bg:  #FFFBEB
--color-error:       #DC2626    Fehler, Storniert
--color-error-bg:    #FEF2F2
--color-info:        #0284C7    Information, Hinweis
--color-info-bg:     #F0F9FF

OBERFLÄCHEN
--color-surface:     #FFFFFF    Karten, Modals
--color-page-bg:     #FAFAF9    Seitenhintergrund
--color-sidebar-bg:  #F5F5F4    Sidebar
--color-header-bg:   #FFFFFF    Header
```

**Begründung (Marco):** Healthcare-Teal vermittelt Vertrauen, Ruhe und Professionalität.
Es unterscheidet OMNIA von generischen Business-Apps und schafft eine eigenständige Identität.
Die wärmeren Grautöne wirken einladender als die kalten Blau-Grautöne.

### 2.3 Typografie

```
FONT-STACK (Upgrade auf Inter für bessere Lesbarkeit)
--font-family-primary: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif
--font-family-mono:    'JetBrains Mono', 'Fira Code', monospace

TYPE SCALE (modular, 1.25 ratio)
--text-xs:    0.75rem   / 1rem      (12px) - Captions, Timestamps
--text-sm:    0.8125rem / 1.25rem   (13px) - Labels, Badges
--text-base:  0.875rem  / 1.5rem    (14px) - Body Text
--text-md:    1rem      / 1.5rem    (16px) - Lead Text
--text-lg:    1.125rem  / 1.75rem   (18px) - Section Headers
--text-xl:    1.25rem   / 1.75rem   (20px) - Card Titles
--text-2xl:   1.5rem    / 2rem      (24px) - Page Titles
--text-3xl:   1.875rem  / 2.25rem   (30px) - Hero Headings

FONT WEIGHTS
--font-normal:    400   Body
--font-medium:    500   Labels, Navigation
--font-semibold:  600   Headings, Buttons
--font-bold:      700   Page Titles
```

**Begründung (Marco):** Inter ist die meistgenutzte UI-Schrift 2024/25, optimiert für Bildschirme,
mit hervorragender Lesbarkeit bei kleinen Grössen und breiter Sprachunterstützung.
Self-hosted via `/static/fonts/` für DSGVO-Konformität.

### 2.4 Spacing & Layout

```
SPACING SCALE (8px Basis)
--space-0:   0
--space-1:   0.25rem  (4px)
--space-2:   0.5rem   (8px)
--space-3:   0.75rem  (12px)
--space-4:   1rem     (16px)
--space-5:   1.25rem  (20px)
--space-6:   1.5rem   (24px)
--space-8:   2rem     (32px)
--space-10:  2.5rem   (40px)
--space-12:  3rem     (48px)
--space-16:  4rem     (64px)

LAYOUT
--sidebar-width:      240px
--sidebar-collapsed:  64px
--header-height:      60px
--content-max-width:  1400px
--chat-width:         380px

BORDER RADIUS (etwas runder, moderner)
--radius-sm:   6px     Buttons, Inputs
--radius-md:   8px     Cards, Badges
--radius-lg:   12px    Modals, grosse Cards
--radius-xl:   16px    Hero-Elemente
--radius-full: 9999px  Pills, Avatare
```

### 2.5 Schatten & Tiefe

```
ELEVATION SYSTEM (subtiler, moderner)
--shadow-xs:  0 1px 2px 0 rgb(0 0 0 / 0.03)
--shadow-sm:  0 1px 3px 0 rgb(0 0 0 / 0.04), 0 1px 2px -1px rgb(0 0 0 / 0.04)
--shadow-md:  0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05)
--shadow-lg:  0 10px 15px -3px rgb(0 0 0 / 0.06), 0 4px 6px -4px rgb(0 0 0 / 0.06)
--shadow-xl:  0 20px 25px -5px rgb(0 0 0 / 0.08), 0 8px 10px -6px rgb(0 0 0 / 0.08)

FOCUS RING (konsistent, zugänglich)
--ring-width:  2px
--ring-color:  var(--color-primary-400)
--ring-offset: 2px
--ring:        0 0 0 var(--ring-offset) white, 0 0 0 calc(var(--ring-offset) + var(--ring-width)) var(--ring-color)
```

### 2.6 Komponentensystem (Sarah Kim, David Brunner)

#### Buttons (neu)
```
HIERARCHIE:
.btn-primary    - Teal gefüllt, weiss Text (Hauptaktion)
.btn-secondary  - Teal Outline (Sekundäre Aktion)
.btn-tertiary   - Nur Text, Teal Farbe (Tertiäre Aktion)
.btn-danger     - Rot gefüllt (Destruktive Aktion)
.btn-ghost      - Transparent, grauer Text (Subtle)

GRÖSSEN:
.btn-xs   - 28px Höhe, text-xs
.btn-sm   - 32px Höhe, text-sm
.btn-md   - 36px Höhe, text-base (Default)
.btn-lg   - 44px Höhe, text-md

STATES:
:hover     - 1 Stufe dunkler + shadow-sm
:active    - 2 Stufen dunkler
:focus     - Focus Ring
:disabled  - 50% Opacity, cursor: not-allowed
:loading   - Spinner-Icon, pointer-events: none
```

#### Cards (neu)
```
.card                - Weiss, radius-lg, shadow-sm, border neutral-200
.card-header         - Flex, padding space-4, border-bottom
.card-body           - Padding space-4
.card-footer         - Flex, padding space-4, border-top, bg neutral-50

VARIANTEN:
.card-elevated       - shadow-md statt shadow-sm
.card-interactive    - Hover: shadow-md + translateY(-1px)
.card-accent-left    - 3px linker Rand in Primärfarbe
.card-highlight      - Border in primary-200, bg primary-50
```

#### Formulare (neu, vereinheitlicht)
```
.form-field          - Wrapper für Label + Input + Hint + Error
.form-label          - text-sm, font-medium, neutral-700
.form-input          - 36px Höhe, radius-sm, border neutral-300
.form-select         - Wie Input + Custom Chevron
.form-textarea       - Min-height 80px, resize vertical
.form-hint           - text-xs, neutral-500
.form-error          - text-xs, error-500, mit Icon

STATES:
:focus       - Primary border + Focus Ring
:invalid     - Error border + Error message
:disabled    - bg neutral-100, cursor: not-allowed

LAYOUTS:
.form-row            - Flex-Row, gap space-4
.form-grid           - CSS Grid, auto-fit minmax(280px, 1fr)
.form-section        - Gruppierung mit Titel + Divider
.form-actions        - Sticky Footer mit Buttons rechts
```

#### Tabellen (neu)
```
.data-table          - Einheitlicher Name (ersetzt .table)
.data-table thead    - bg neutral-50, text-xs, uppercase, tracking-wider
.data-table tbody tr - Hover: bg neutral-50, transition
.data-table td       - padding space-3, border-bottom neutral-100

FEATURES:
.table-sortable th   - Cursor pointer + Sort-Icon
.table-selectable    - Checkbox-Spalte + Batch-Actions
.table-sticky-header - Sticky Header beim Scrollen
.table-responsive    - Horizontaler Scroll auf Mobile
```

#### Badges & Status (neu)
```
BADGES (mit Icon-Support):
.badge               - Inline-Flex, radius-full, text-xs, font-medium
.badge-{color}       - primary, success, warning, error, neutral
.badge-dot           - 8px Punkt + Text (für Status-Listen)
.badge-count         - Numerischer Counter (Navigation)

STATUS INDICATORS (Farbe + Icon, nie nur Farbe):
.status-active       - Grüner Punkt + "Aktiv" Text
.status-inactive     - Grauer Punkt + "Inaktiv" Text
.status-pending      - Gelber Punkt + "Ausstehend" Text
.status-error        - Roter Punkt + "Fehler" Text
```

#### Navigation (neu)
```
SIDEBAR:
- Wärmerer Hintergrund (neutral-100)
- Grössere Touch-Targets (44px Höhe)
- Icon + Label immer sichtbar (auch collapsed via Tooltip)
- Aktiver State: primary-50 bg + primary-500 left-border
- Gruppierung mit Sections + Überschriften
- Collapsed: Tooltips on Hover

HEADER:
- Klarere Trennung: Logo | Breadcrumb | Search | Actions | User
- Globale Suche: Command Palette Style (Cmd+K)
- Notifications: Dropdown mit gruppierten Items
- User Menu: Avatar + Name + Role sichtbar
```

#### Modals (neu)
```
.modal-overlay       - Backdrop blur(4px) + rgba(0,0,0,0.4)
.modal-panel         - radius-lg, shadow-xl, max-height 85vh
.modal-header        - Flex, space-between, padding space-5
.modal-body          - Padding space-5, overflow-y auto
.modal-footer        - Flex, justify-end, gap space-3, border-top

SIZES:
.modal-sm            - max-width 420px (Confirmations)
.modal-md            - max-width 560px (Formulare)
.modal-lg            - max-width 800px (Detail-Ansichten)
.modal-xl            - max-width 1100px (Komplexe Workflows)
.modal-full          - 95vw x 90vh (Vollbild)

ANIMATION:
- Overlay: Fade-in 200ms
- Panel: Scale(0.95) + Fade-in 250ms ease-out
- Close: Reverse 150ms
- Focus Trap: Automatisch

CONFIRMATION DIALOG (ersetzt confirm()):
.confirm-dialog      - modal-sm
- Icon (Warnung/Frage)
- Titel + Beschreibung
- Cancel + Confirm Buttons
- Destruktiv: Confirm in Rot
```

### 2.7 Seitenspezifische Redesign-Konzepte

#### Dashboard (Lena Hartmann)
```
AKTUELL:  Grid mit gleichförmigen Widget-Cards
NEU:      Priorisierte Ansicht mit Fokuszonen

LAYOUT:
┌──────────────────────────────────────────────┐
│  Guten Morgen, Thomas        [Di, 24. März]  │  Greeting Bar
├──────────────┬───────────────────────────────┤
│              │                               │
│  HEUTE       │  NÄCHSTE TERMINE              │  Hero Zone
│  8 Termine   │  09:00 Müller - Physio        │  (grösser, prominenter)
│  2 offen     │  09:45 Schmidt - Erstbef.     │
│              │  10:30 Weber - Nachkontrolle  │
├──────────────┴───────────────────────────────┤
│  Aufgaben (3)  │  KI-Tipp  │  Geburtstage   │  Quick Info Row
├──────────────────────────────────────────────┤
│  Auslastung    │  Umsatz   │  Off. Rechnungen│  Metrics Row
└──────────────────────────────────────────────┘

VERBESSERUNGEN:
- Persönliche Begrüssung mit Tagesübersicht
- Hero-Zone: Die wichtigsten Infos sofort sichtbar
- KI-Tagesübersicht prominent statt als Widget
- Schnellaktionen: Floating Action Button (FAB) statt Grid
- Drag & Drop Widget-Anordnung
```

#### Kalender (Sarah Kim)
```
AKTUELL:  Funktional, aber visuelle Dichte hoch
NEU:      Klarere Struktur, bessere Farbcodierung

VERBESSERUNGEN:
- Farbcodierung nach Behandlungstyp (nicht nach Therapeut)
- Hover-Preview: Termin-Details ohne Modal öffnen
- Quick-Add: Klick auf leere Zelle = Inline-Formular
- Drag-Feedback: Geister-Element + Zielzone-Highlight
- Heute-Indikator: Breiterer, farbiger Streifen
- Wochenansicht: Scroll-Sync zwischen Therapeuten
- Mobile: Swipe-Navigation zwischen Tagen
```

#### Patientenliste (Nina Vogt)
```
AKTUELL:  Tabelle mit Filterbalkens
NEU:      Hybride Ansicht (Liste + Karten umschaltbar)

VERBESSERUNGEN:
- Listenansicht: Kompakter, mit Avatar-Initialen
- Kartenansicht: Für visuellen Überblick
- Erweiterte Suche: Sofort-Filter (kein Submit-Button)
- Quick Actions: Hover-Aktionen pro Zeile (Termin, E-Mail)
- Letzte Behandlung: Datum + Typ direkt in der Liste
- Status-Chips statt Farbcodierte Zeilen
```

#### Patienten-Detail (Lena Hartmann)
```
AKTUELL:  Header + Tabs + Detail-Grid
NEU:      Timeline-zentrierte Patientenakte

LAYOUT:
┌─────────────────────────────────────────────┐
│  [Avatar] Max Mustermann           [Edit]   │
│  Geb: 15.03.1985  │  Vers: CSS  │  Aktiv   │
├─────────────┬───────────────────────────────┤
│             │                               │
│  NAVIGATION │  TIMELINE                     │
│  Übersicht  │  ┌─ 24.03 Behandlung ─────┐  │
│  Behandlung │  │  Physio, 45min, Dr. M.  │  │
│  Dokumente  │  └────────────────────────-┘  │
│  Termine    │  ┌─ 20.03 Rechnung ────────┐  │
│  Abrechnung │  │  CHF 180.00, bezahlt    │  │
│  Kommunik.  │  └────────────────────────-┘  │
│  Portal     │  ┌─ 18.03 Dokument ────────┐  │
│             │  │  MRI-Bericht hochgeladen │  │
│             │  └─────────────────────────-┘  │
└─────────────┴───────────────────────────────┘

VERBESSERUNGEN:
- Chronologische Timeline als Hauptansicht
- Seitliche Navigation statt Tabs (immer sichtbar)
- Quick-Actions im Header (Termin buchen, E-Mail senden)
- Behandlungsfortschritt als visueller Balken
- Dokumente: Drag & Drop Upload
```

### 2.8 Micro-Interactions & Animationen (Sarah Kim)

```
TRANSITIONS:
--duration-fast:    100ms   Button-States, Toggles
--duration-base:    200ms   Hover-Effekte, Farb-Übergänge
--duration-slow:    300ms   Panel-Slides, Modale
--duration-enter:   250ms   Erscheinen (ease-out)
--duration-exit:    200ms   Verschwinden (ease-in)

EASING:
--ease-in:     cubic-bezier(0.4, 0, 1, 0.5)
--ease-out:    cubic-bezier(0, 0, 0.2, 1)
--ease-in-out: cubic-bezier(0.4, 0, 0.2, 1)
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1)

NEUE ANIMATIONEN:
- Seiten-Übergang: Fade + SlideUp (150ms)
- Toast: SlideIn von rechts + leichte Bounce
- Modal: Scale(0.95→1) + Fade
- Skeleton Loading: Pulsierender Gradient statt "Laden..."
- Erfolgs-Check: Animiertes Häkchen-SVG
- Tab-Wechsel: Content Crossfade
- Sidebar-Collapse: Smooth Width-Transition
- Card-Hover: translateY(-2px) + Shadow-Erhöhung
- Button-Click: Scale(0.97) kurz
- Badge-Counter: Pop-in Animation bei Änderung
```

### 2.9 Accessibility-Konzept (Sarah Kim)

```
WCAG 2.1 AA COMPLIANCE:

1. KONTRASTE
   - Text auf Weiss: Minimum 4.5:1 (aktuell teilweise 3:1)
   - Grosser Text: Minimum 3:1
   - UI-Elemente: Minimum 3:1 gegen Hintergrund

2. KEYBOARD NAVIGATION
   - Skip-Link: "Zum Hauptinhalt springen"
   - Focus Ring: Sichtbar, 2px primary-400
   - Tab-Reihenfolge: Logisch, von oben nach unten
   - Shortcuts: Cmd+K (Suche), Esc (Modal schliessen)

3. SCREEN READER
   - ARIA Landmarks: banner, navigation, main, complementary
   - Live Regions: Notifications, Toast-Meldungen
   - ARIA Labels: Alle Icon-Buttons
   - Status Updates: aria-live="polite"

4. VISUELLE UNTERSTÜTZUNG
   - Status: Farbe + Icon + Text (nie nur Farbe)
   - Fokus: Immer sichtbar, nie nur outline: none
   - Fehler: Rot + Icon + Text + aria-invalid
   - Ladezustand: Skeleton + aria-busy="true"

5. MOTORISCHE UNTERSTÜTZUNG
   - Touch Targets: Minimum 44x44px
   - Hover-Aktionen: Auch per Keyboard erreichbar
   - Drag & Drop: Alternative Buttons vorhanden
```

### 2.10 Dark Mode Konzept (Marco Berchtold)

```
DARK MODE PALETTE:
--color-page-bg:     #1A1A1A
--color-surface:     #242424
--color-surface-2:   #2E2E2E
--color-border:      #3A3A3A
--color-text:        #E5E5E5
--color-text-muted:  #999999
--color-primary-500: #2DB5B5  (heller als Light Mode)

IMPLEMENTIERUNG:
- CSS: @media (prefers-color-scheme: dark) + .theme-dark Klasse
- Toggle: Im User-Menu (System / Hell / Dunkel)
- Speicherung: localStorage + User-Einstellung in DB
- Bilder: Angepasste Opacity für Logos/Icons
```

---

## Teil 3: Umbauplan

### Phase 0: Fundament (Woche 1-2)

**Ziel:** Design Tokens und CSS-Architektur aufräumen

```
AUFGABEN:
□ Design Tokens Datei erstellen: static/css/tokens.css
  - Alle Farben, Spacing, Typography, Shadows, Radii
  - Light Mode + Dark Mode Variablen

□ Inter Font self-hosted einbinden
  - Download: Inter Regular (400), Medium (500), SemiBold (600), Bold (700)
  - Ablegen in: static/fonts/inter/
  - @font-face Deklarationen in tokens.css

□ CSS-Dateien konsolidieren
  - portal.css: Eigene Variablen → Root-Variablen migrieren
  - calendar.css: --gray-* → --color-neutral-* Variablen
  - treatment.css: Hardcoded Werte → CSS Variablen

□ Einheitliche Klassen definieren
  - .table → .data-table (überall)
  - .form-control → .form-input (überall)
  - .form-label → konsistent

□ Inline-Styles entfernen
  - patients/form.html Inline-Styles → CSS-Klassen
  - Alle Templates auf Inline-Styles prüfen

DATEIEN:
  - NEU: static/css/tokens.css
  - EDIT: static/css/style.css (Variablen ersetzen)
  - EDIT: static/css/portal.css (Variablen migrieren)
  - EDIT: static/css/calendar.css (Variablen korrigieren)
  - EDIT: static/css/treatment.css (Hardcoded ersetzen)
  - EDIT: templates/base.html (Font + tokens.css laden)
```

### Phase 1: Kern-Komponenten (Woche 3-5)

**Ziel:** Neues Komponentensystem implementieren

```
AUFGABEN:
□ Buttons
  - Neue Button-Klassen mit Teal-Palette
  - Alle Grössen (xs, sm, md, lg)
  - Loading-State mit Spinner
  - Alle Templates aktualisieren

□ Cards
  - Neue Card-Varianten (elevated, interactive, accent)
  - Widget-Cards auf neues System umstellen
  - Dashboard-Widgets migrieren

□ Formulare
  - Einheitliches .form-field System
  - Inline-Validation mit Error-Messages
  - Alle Formulare migrieren (Patienten, Mitarbeiter, etc.)

□ Tabellen
  - .data-table Redesign
  - Sortierbare Spalten
  - Sticky Header
  - Responsive Wrapper
  - Alle Tabellen migrieren

□ Badges & Status
  - Neue Badge-Varianten
  - Status-Indikatoren mit Icon + Text
  - Templates aktualisieren

□ Modals
  - Backdrop Blur + neue Animationen
  - Focus Trap implementieren
  - Confirmation Dialog Komponente
  - confirm() überall ersetzen

DATEIEN:
  - EDIT: static/css/style.css (Komponenten)
  - EDIT: static/js/app.js (Modal Focus Trap, Confirmations)
  - EDIT: Alle blueprint templates
```

### Phase 2: Layout & Navigation (Woche 6-7)

**Ziel:** Sidebar, Header und Seitenstruktur modernisieren

```
AUFGABEN:
□ Header Redesign
  - Neues Layout: Logo | Breadcrumb | Suche | Actions | User
  - Command Palette Suche (Cmd+K)
  - Notification Dropdown
  - User Menu mit Avatar + Rolle

□ Sidebar Redesign
  - Wärmere Farben (neutral-100)
  - Grössere Touch-Targets (44px)
  - Section-Gruppierung
  - Tooltips bei collapsed State
  - Smooth Collapse-Animation

□ Page Layout
  - Konsistente Page-Header (Titel + Actions)
  - Breadcrumb-Standardisierung
  - Content Max-Width (1400px)
  - Besseres Spacing zwischen Sektionen

□ Responsive Überarbeitung
  - Mobile Sidebar: Bottom-Navigation optimieren
  - Tablet: 2-Spalten-Layouts verbessern
  - Touch-Targets überall >= 44px

DATEIEN:
  - EDIT: templates/base.html
  - EDIT: static/css/style.css
  - EDIT: static/js/app.js (Command Palette, Sidebar)
```

### Phase 3: Seiten-Redesigns (Woche 8-12)

**Ziel:** Schlüsselseiten nach neuem Konzept umbauen

```
WOCHE 8-9: DASHBOARD
□ Greeting Bar + Hero Zone
□ Priorisierte Widget-Anordnung
□ KI-Tagesübersicht prominent
□ Metrics Row mit Mini-Charts
□ Schnellaktionen als FAB

WOCHE 9-10: KALENDER
□ Bessere Farbcodierung
□ Hover-Preview für Termine
□ Quick-Add Inline-Formular
□ Drag & Drop Feedback
□ Mobile Swipe-Navigation

WOCHE 10-11: PATIENTEN
□ Liste: Sofort-Filter, Quick Actions
□ Ansicht-Toggle (Liste/Karten)
□ Detail: Timeline-View
□ Behandlungsfortschritt visuell

WOCHE 11-12: ABRECHNUNG & HR
□ Rechnungsliste mit Tabs modernisieren
□ Rechnungsformular: Schrittweise Erfassung
□ HR Dashboard mit Übersichts-Karten
□ Lohnabrechnungs-Workflow visuell

DATEIEN:
  - EDIT: blueprints/dashboard/templates/*
  - EDIT: blueprints/calendar/templates/*
  - EDIT: blueprints/patients/templates/*
  - EDIT: blueprints/billing/templates/*
  - EDIT: blueprints/hr/templates/*
  - EDIT: static/css/dashboard.css
  - EDIT: static/css/calendar.css
  - EDIT: static/js/dashboard.js
  - EDIT: static/js/calendar.js
```

### Phase 4: Accessibility & Polish (Woche 13-14)

**Ziel:** WCAG 2.1 AA Konformität und Feinschliff

```
AUFGABEN:
□ Skip-Links einbauen
□ ARIA Landmarks in base.html
□ Alle Icon-Buttons: aria-label
□ Focus-Management: Modals, Dropdowns
□ Kontrastprüfung aller Texte
□ Keyboard-Navigation testen
□ Screen Reader Testing (VoiceOver)
□ Skeleton Loading States
□ Micro-Interactions / Animationen
□ Loading Spinners vereinheitlichen
□ Error States für alle Formulare
□ Empty States visuell aufwerten
□ Toast Animationen verbessern
```

### Phase 5: Theming & Dark Mode (Woche 15-16)

**Ziel:** Dark Mode und Theming-Infrastruktur

```
AUFGABEN:
□ Dark Mode CSS Variablen
□ @media prefers-color-scheme Support
□ Theme Toggle in User Menu
□ Theme Preference in DB speichern
□ Alle Komponenten im Dark Mode testen
□ Logo/Icon Anpassungen für Dark Mode
□ Portal: Eigenes Theme (patientenfreundlich)
```

---

## Zusammenfassung

### Vorher → Nachher

| Aspekt | Vorher | Nachher |
|--------|--------|---------|
| Farbpalette | Generisches Blau (#4a90d9) | Healthcare-Teal (#1a8f8f) |
| Typografie | System Fonts | Inter (self-hosted) |
| Komponenten | Inkonsistent (6 CSS-Dateien) | Unified Design System |
| Formulare | 3 verschiedene Patterns | 1 einheitliches System |
| Tabellen | .table vs .data-table | .data-table überall |
| Modals | Browser confirm() | Gestylte Confirmation Dialogs |
| Accessibility | 5/10 | 9/10 (WCAG 2.1 AA) |
| Dark Mode | Nicht vorhanden | Vollständig implementiert |
| Animationen | Minimal | Durchdachte Micro-Interactions |
| Mobile | Grundlegend | Touch-optimiert, 44px Targets |

### Erwarteter Design Score nach Umbau: 92/100

| Bereich | Vorher | Nachher |
|---------|--------|---------|
| Farbsystem | 8/10 | 10/10 |
| Typografie | 9/10 | 10/10 |
| Spacing | 7/10 | 9/10 |
| Komponenten | 6/10 | 9/10 |
| Formulare | 5/10 | 9/10 |
| Responsive | 6/10 | 9/10 |
| Barrierefreiheit | 5/10 | 9/10 |
| Gesamteindruck | 6/10 | 9/10 |
