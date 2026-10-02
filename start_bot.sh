#!/bin/bash
ROOT="$(cd "$(dirname "$0")" && pwd)"
MAIN="$ROOT/main.py"
PID_PATTERN="python.*${MAIN}"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/bot.log"

activate_venv() {
  if [ -n "${VENV:-}" ] && [ -f "$VENV" ]; then
    # shellcheck source=/dev/null
    source "$VENV"
  elif [ -f "$ROOT/venv/bin/activate" ]; then
    # shellcheck source=/dev/null
    source "$ROOT/venv/bin/activate"
  elif [ -f "$ROOT/myenv/bin/activate" ]; then
    # shellcheck source=/dev/null
    source "$ROOT/myenv/bin/activate"
  fi
}

bot_pids() {
  pgrep -f "$PID_PATTERN" 2>/dev/null || true
}

stop_bot() {
  local pids
  pids="$(bot_pids)"
  if [ -z "$pids" ]; then
    echo "Bot is not running"
    return 0
  fi
  echo "Stopping bot (PID: $pids)..."
  kill $pids 2>/dev/null || true
  sleep 1
  pids="$(bot_pids)"
  if [ -n "$pids" ]; then
    kill -9 $pids 2>/dev/null || true
    sleep 1
  fi
  if [ -n "$(bot_pids)" ]; then
    echo "Failed to stop bot"
    return 1
  fi
  echo "Bot stopped"
}

start_bot() {
  if [ -n "$(bot_pids)" ]; then
    echo "Bot already running (PID: $(bot_pids))"
    return 0
  fi
  mkdir -p "$LOG_DIR"
  activate_venv
  cd "$ROOT"
  nohup python3 "$MAIN" >> "$LOG_FILE" 2>&1 &
  sleep 1
  if [ -n "$(bot_pids)" ]; then
    echo "Bot started (PID: $(bot_pids), log: $LOG_FILE)"
  else
    echo "Failed to start bot — see $LOG_FILE"
    return 1
  fi
}

restart_bot() {
  stop_bot || return 1
  start_bot
}

usage() {
  echo "Usage: $0 [start|restart|stop]"
  echo "  start   — run if not already running"
  echo "  restart — stop then start (default)"
  echo "  stop    — stop running instance"
  echo ""
  echo "Optional: VENV=/path/to/venv/bin/activate"
}

cmd="${1:-restart}"
case "$cmd" in
  start) start_bot ;;
  restart) restart_bot ;;
  stop) stop_bot ;;
  -h|--help|help) usage ;;
  *)
    echo "Unknown command: $cmd"
    usage
    exit 1
    ;;
esac
