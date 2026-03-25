#!/usr/bin/env bash
# ============================================================================
# OMNIA Praxissoftware - Security Hardening Orchestrator
# Multi-Agent Programm fuer strukturierte Sicherheitshaertung
# ============================================================================
#
# Ausfuehrung:  cd /Users/thomasbalke/praxis-app && bash security-hardening/run.sh
#
# Optionen:
#   --phase N        Nur Phase N ausfuehren (1-8)
#   --from  N        Ab Phase N starten
#   --dry-run        Nur anzeigen, was gemacht wird
#   --skip-validate  Validierung ueberspringen
#
# ============================================================================

set -euo pipefail

# --- Konfiguration ---
PROJECT_DIR="/Users/thomasbalke/praxis-app"
HARDENING_DIR="$PROJECT_DIR/security-hardening"
PROMPTS_DIR="$HARDENING_DIR/prompts"
LOG_DIR="$HARDENING_DIR/logs"
VALIDATORS_DIR="$HARDENING_DIR/validators"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MAIN_LOG="$LOG_DIR/run_${TIMESTAMP}.log"

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- Argumente parsen ---
PHASE_ONLY=""
PHASE_FROM=1
DRY_RUN=false
SKIP_VALIDATE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --phase)    PHASE_ONLY="$2"; shift 2 ;;
        --from)     PHASE_FROM="$2"; shift 2 ;;
        --dry-run)  DRY_RUN=true; shift ;;
        --skip-validate) SKIP_VALIDATE=true; shift ;;
        *)          echo "Unbekannte Option: $1"; exit 1 ;;
    esac
done

# --- Hilfsfunktionen ---
log() {
    local msg="[$(date '+%H:%M:%S')] $1"
    echo -e "$msg" | tee -a "$MAIN_LOG"
}

header() {
    echo "" | tee -a "$MAIN_LOG"
    echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════════════${NC}" | tee -a "$MAIN_LOG"
    echo -e "${BOLD}${BLUE}  $1${NC}" | tee -a "$MAIN_LOG"
    echo -e "${BOLD}${BLUE}═══════════════════════════════════════════════════════════════${NC}" | tee -a "$MAIN_LOG"
    echo "" | tee -a "$MAIN_LOG"
}

subheader() {
    echo -e "\n${CYAN}  ── $1 ──${NC}\n" | tee -a "$MAIN_LOG"
}

success() {
    echo -e "  ${GREEN}✓${NC} $1" | tee -a "$MAIN_LOG"
}

warn() {
    echo -e "  ${YELLOW}⚠${NC} $1" | tee -a "$MAIN_LOG"
}

fail() {
    echo -e "  ${RED}✗${NC} $1" | tee -a "$MAIN_LOG"
}

# Git-Backup erstellen
create_backup() {
    log "Erstelle Git-Backup-Branch: backup/pre-hardening-${TIMESTAMP}"
    cd "$PROJECT_DIR"
    git stash --include-untracked -m "pre-hardening-backup-${TIMESTAMP}" 2>/dev/null || true
    git stash pop 2>/dev/null || true
    git checkout -b "backup/pre-hardening-${TIMESTAMP}" 2>/dev/null || true
    git checkout - 2>/dev/null || true
    success "Backup-Branch erstellt"
}

# Agent ausfuehren
run_agent() {
    local agent_name="$1"
    local prompt_file="$2"
    local agent_log="$LOG_DIR/${agent_name}_${TIMESTAMP}.log"

    if [ "$DRY_RUN" = true ]; then
        warn "[DRY-RUN] Wuerde Agent '$agent_name' ausfuehren mit Prompt: $prompt_file"
        return 0
    fi

    subheader "Agent: $agent_name"
    log "Starte Agent '$agent_name'..."
    log "Prompt: $prompt_file"
    log "Log: $agent_log"

    # Claude Code im nicht-interaktiven Modus ausfuehren
    if claude -p "$(cat "$prompt_file")" \
        --output-format text \
        --max-turns 50 \
        --allowedTools "Edit,Write,Read,Glob,Grep,Bash(safe)" \
        > "$agent_log" 2>&1; then
        success "Agent '$agent_name' erfolgreich abgeschlossen"
        return 0
    else
        fail "Agent '$agent_name' mit Fehler beendet (siehe $agent_log)"
        return 1
    fi
}

# Zwei Agenten parallel ausfuehren
run_agents_parallel() {
    local agent1_name="$1"
    local prompt1="$2"
    local agent2_name="$3"
    local prompt2="$4"

    if [ "$DRY_RUN" = true ]; then
        warn "[DRY-RUN] Wuerde parallel ausfuehren: '$agent1_name' + '$agent2_name'"
        return 0
    fi

    subheader "Parallel: $agent1_name + $agent2_name"

    local log1="$LOG_DIR/${agent1_name}_${TIMESTAMP}.log"
    local log2="$LOG_DIR/${agent2_name}_${TIMESTAMP}.log"

    # Parallel starten
    claude -p "$(cat "$prompt1")" \
        --output-format text \
        --max-turns 50 \
        --allowedTools "Edit,Write,Read,Glob,Grep,Bash(safe)" \
        > "$log1" 2>&1 &
    local pid1=$!

    claude -p "$(cat "$prompt2")" \
        --output-format text \
        --max-turns 50 \
        --allowedTools "Edit,Write,Read,Glob,Grep,Bash(safe)" \
        > "$log2" 2>&1 &
    local pid2=$!

    # Auf beide warten
    local failed=0
    wait $pid1 || { fail "Agent '$agent1_name' fehlgeschlagen"; failed=1; }
    wait $pid2 || { fail "Agent '$agent2_name' fehlgeschlagen"; failed=1; }

    [ $failed -eq 0 ] && success "Beide Agenten erfolgreich"
    return $failed
}

# Validierungs-Agent ausfuehren
run_validator() {
    local phase_name="$1"
    local validator_prompt="$2"

    if [ "$SKIP_VALIDATE" = true ]; then
        warn "Validierung uebersprungen (--skip-validate)"
        return 0
    fi

    subheader "Validierung: $phase_name"

    local val_log="$LOG_DIR/validate_${phase_name}_${TIMESTAMP}.log"

    if claude -p "$(cat "$validator_prompt")" \
        --output-format text \
        --max-turns 20 \
        --allowedTools "Read,Glob,Grep,Bash(safe)" \
        > "$val_log" 2>&1; then
        success "Validierung '$phase_name' bestanden"
        return 0
    else
        fail "Validierung '$phase_name' fehlgeschlagen (siehe $val_log)"
        return 1
    fi
}

# Phase ausfuehren wenn zutreffend
should_run_phase() {
    local phase_num=$1
    if [ -n "$PHASE_ONLY" ]; then
        [ "$PHASE_ONLY" -eq "$phase_num" ]
    else
        [ "$phase_num" -ge "$PHASE_FROM" ]
    fi
}

# Git-Commit nach Phase
commit_phase() {
    local phase_name="$1"
    cd "$PROJECT_DIR"
    if git diff --quiet && git diff --cached --quiet; then
        warn "Keine Aenderungen zum Committen in Phase: $phase_name"
    else
        git add -A
        git commit -m "security-hardening: $phase_name

Automatisierte Sicherheitshaertung durch Multi-Agent-System.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
        success "Commit erstellt fuer: $phase_name"
    fi
}

# ============================================================================
# HAUPTPROGRAMM
# ============================================================================

header "OMNIA Praxissoftware - Security Hardening"
log "Gestartet: $(date)"
log "Projekt: $PROJECT_DIR"
log "Optionen: phase_only=$PHASE_ONLY, from=$PHASE_FROM, dry_run=$DRY_RUN"
echo ""

# Voraussetzungen pruefen
if ! command -v claude &> /dev/null; then
    fail "Claude Code CLI nicht gefunden. Bitte installieren: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

if [ ! -d "$PROJECT_DIR/.git" ]; then
    fail "Kein Git-Repository in $PROJECT_DIR"
    exit 1
fi

# Backup
create_backup

# ============================================================================
# PHASE 1: Kritische Sofort-Fixes (Keine Abhaengigkeiten)
# ============================================================================
if should_run_phase 1; then
    header "PHASE 1/8: Kritische Sofort-Fixes"
    log "Behebe die gefaehrlichsten Luecken zuerst."
    log "3 Agenten arbeiten parallel an unabhaengigen Bereichen."

    # Agent 1a + 1b parallel: Auth-Fixes + Config-Fixes
    run_agents_parallel \
        "phase1_auth_fixes" "$PROMPTS_DIR/phase1a_auth_fixes.md" \
        "phase1_config_fixes" "$PROMPTS_DIR/phase1b_config_security.md"

    # Agent 1c: Portal-Fixes (haengt nicht von 1a/1b ab)
    run_agent "phase1_portal_fixes" "$PROMPTS_DIR/phase1c_portal_fixes.md"

    # Validierung
    run_validator "phase1" "$VALIDATORS_DIR/validate_phase1.md"

    commit_phase "Phase 1 - Kritische Sofort-Fixes"
    success "PHASE 1 ABGESCHLOSSEN"
fi

# ============================================================================
# PHASE 2: Datenverschluesselung
# ============================================================================
if should_run_phase 2; then
    header "PHASE 2/8: Datenverschluesselung"
    log "Implementiert Feld-Level-Verschluesselung fuer sensible Daten."
    log "2 Agenten: Encryption-Framework + Feld-Migration."

    # Agent 2a: Encryption Framework erstellen
    run_agent "phase2_encryption_framework" "$PROMPTS_DIR/phase2a_encryption_framework.md"

    # Agent 2b: Felder verschluesseln (braucht Framework von 2a)
    run_agent "phase2_field_encryption" "$PROMPTS_DIR/phase2b_field_encryption.md"

    # Validierung
    run_validator "phase2" "$VALIDATORS_DIR/validate_phase2.md"

    commit_phase "Phase 2 - Datenverschluesselung"
    success "PHASE 2 ABGESCHLOSSEN"
fi

# ============================================================================
# PHASE 3: Authentifizierung & Zugriffskontrolle
# ============================================================================
if should_run_phase 3; then
    header "PHASE 3/8: Authentifizierung & Zugriffskontrolle"
    log "2FA, Account-Lockout, RBAC, Session-Haertung."
    log "2 Agenten parallel: Auth-Haertung + RBAC."

    run_agents_parallel \
        "phase3_auth_hardening" "$PROMPTS_DIR/phase3a_auth_hardening.md" \
        "phase3_rbac" "$PROMPTS_DIR/phase3b_rbac.md"

    # Validierung
    run_validator "phase3" "$VALIDATORS_DIR/validate_phase3.md"

    commit_phase "Phase 3 - Auth und RBAC"
    success "PHASE 3 ABGESCHLOSSEN"
fi

# ============================================================================
# PHASE 4: KI-System Sicherheit
# ============================================================================
if should_run_phase 4; then
    header "PHASE 4/8: KI-System Sicherheit"
    log "Tool-Permissions, PII-Filter, Bestaetigungssystem."
    log "2 Agenten parallel: Tool-Security + PII-Filter."

    run_agents_parallel \
        "phase4_tool_security" "$PROMPTS_DIR/phase4a_tool_security.md" \
        "phase4_pii_filter" "$PROMPTS_DIR/phase4b_pii_filter.md"

    # Validierung
    run_validator "phase4" "$VALIDATORS_DIR/validate_phase4.md"

    commit_phase "Phase 4 - KI-System Sicherheit"
    success "PHASE 4 ABGESCHLOSSEN"
fi

# ============================================================================
# PHASE 5: Audit-Logging & Compliance
# ============================================================================
if should_run_phase 5; then
    header "PHASE 5/8: Audit-Logging & Compliance"
    log "Vollstaendiges Audit-Logging, SOAP-Versionierung, Rechnungs-Immutabilitaet."
    log "3 Agenten: Audit + SOAP-History + Billing-Integrity."

    # Agent 5a: Audit-System erweitern
    run_agent "phase5_audit_system" "$PROMPTS_DIR/phase5a_audit_system.md"

    # Agent 5b + 5c parallel: SOAP + Billing (brauchen Audit-System)
    run_agents_parallel \
        "phase5_soap_versioning" "$PROMPTS_DIR/phase5b_soap_versioning.md" \
        "phase5_billing_integrity" "$PROMPTS_DIR/phase5c_billing_integrity.md"

    # Validierung
    run_validator "phase5" "$VALIDATORS_DIR/validate_phase5.md"

    commit_phase "Phase 5 - Audit und Compliance"
    success "PHASE 5 ABGESCHLOSSEN"
fi

# ============================================================================
# PHASE 6: Infrastruktur-Haertung
# ============================================================================
if should_run_phase 6; then
    header "PHASE 6/8: Infrastruktur-Haertung"
    log "Docker, Nginx, Backup, Dependencies."
    log "2 Agenten parallel: Docker/Nginx + Backup/Deps."

    run_agents_parallel \
        "phase6_docker_nginx" "$PROMPTS_DIR/phase6a_docker_nginx.md" \
        "phase6_backup_deps" "$PROMPTS_DIR/phase6b_backup_deps.md"

    # Validierung
    run_validator "phase6" "$VALIDATORS_DIR/validate_phase6.md"

    commit_phase "Phase 6 - Infrastruktur"
    success "PHASE 6 ABGESCHLOSSEN"
fi

# ============================================================================
# PHASE 7: Test-Suite
# ============================================================================
if should_run_phase 7; then
    header "PHASE 7/8: Test-Suite erstellen"
    log "Sicherheitstests fuer alle gehaerteten Bereiche."
    log "3 Agenten parallel: Auth-Tests + Data-Tests + Integration-Tests."

    # Alle 3 parallel - unabhaengig voneinander
    run_agent "phase7_auth_tests" "$PROMPTS_DIR/phase7a_auth_tests.md" &
    local pid_7a=$!
    run_agent "phase7_data_tests" "$PROMPTS_DIR/phase7b_data_tests.md" &
    local pid_7b=$!
    run_agent "phase7_integration_tests" "$PROMPTS_DIR/phase7c_integration_tests.md" &
    local pid_7c=$!

    wait $pid_7a || fail "Auth-Tests fehlgeschlagen"
    wait $pid_7b || fail "Data-Tests fehlgeschlagen"
    wait $pid_7c || fail "Integration-Tests fehlgeschlagen"

    # Validierung
    run_validator "phase7" "$VALIDATORS_DIR/validate_phase7.md"

    commit_phase "Phase 7 - Test-Suite"
    success "PHASE 7 ABGESCHLOSSEN"
fi

# ============================================================================
# PHASE 8: Abschluss-Validierung & Report
# ============================================================================
if should_run_phase 8; then
    header "PHASE 8/8: Abschluss-Validierung"
    log "Finaler Security-Review durch Review-Agent."

    run_agent "phase8_final_review" "$PROMPTS_DIR/phase8_final_review.md"

    success "PHASE 8 ABGESCHLOSSEN"
fi

# ============================================================================
# ZUSAMMENFASSUNG
# ============================================================================
header "ZUSAMMENFASSUNG"
log "Alle Phasen abgeschlossen."
log "Logs: $LOG_DIR/"
log "Backup-Branch: backup/pre-hardening-${TIMESTAMP}"
echo ""
echo -e "${GREEN}${BOLD}  Naechste Schritte:${NC}"
echo -e "  1. Logs pruefen:  ls $LOG_DIR/"
echo -e "  2. Diff ansehen:  cd $PROJECT_DIR && git diff backup/pre-hardening-${TIMESTAMP}..HEAD"
echo -e "  3. Tests laufen:  cd $PROJECT_DIR && python -m pytest tests/ -v"
echo -e "  4. Manueller Review der Aenderungen"
echo ""
