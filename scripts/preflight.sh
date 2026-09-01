#!/usr/bin/env bash
# =============================================================================
# preflight.sh — đối chiếu MỌI lệnh CLI mà repo này dùng với CLI thật đã cài
# -----------------------------------------------------------------------------
# Vì sao cần: acpx, mcporter, openclaw và clawhub đều đang phát hành nhanh.
# Một cờ có trong tài liệu hôm nay có thể chưa có (hoặc đã đổi tên) trong bản
# bạn vừa cài. Script này dò `--help` của bản THẬT trên máy bạn và báo ngay
# những chỗ lệch, thay vì để bạn phát hiện lúc container đã chạy.
#
# Chạy:  ./scripts/preflight.sh
# Mã trả về: 0 = khớp hết · 1 = có lệch (đọc phần "CẦN SỬA" ở cuối)
# =============================================================================
set -uo pipefail

C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
MISS=0

hdr () { printf '\n%s\n' "$1"; printf '%s\n' "$(printf '─%.0s' $(seq 1 ${#1}))"; }
ok  () { echo "${C_OK}✓${C_OFF} $*"; }
bad () { echo "${C_ERR}✗${C_OFF} $*"; MISS=1; }
skip() { echo "${C_DIM}·${C_OFF} $*"; }

# have <bin>
have () { command -v "$1" >/dev/null 2>&1; }

# check_sub <bin> <subcommand-path...> — kiểm tra một lệnh con có tồn tại
check_sub () {
  local bin="$1"; shift
  local sub="$*"
  if ! have "$bin"; then skip "$bin chưa cài — bỏ qua '$bin $sub'"; return; fi
  local out
  out="$("$bin" $sub --help 2>&1)"
  if grep -qiE 'unknown (command|subcommand)|not a (valid )?command|did you mean' <<<"$out"; then
    bad "$bin $sub — KHÔNG tồn tại trong bản đã cài"
    echo "     ${C_DIM}${out%%$'\n'*}${C_OFF}"
  else
    ok "$bin $sub"
  fi
}

# check_flag <bin> <sub> <flag> — kiểm tra một cờ có trong --help không
check_flag () {
  local bin="$1"; local sub="$2"; local flag="$3"
  if ! have "$bin"; then skip "$bin chưa cài — bỏ qua '$flag'"; return; fi
  local out
  out="$("$bin" $sub --help 2>&1)"
  if grep -qE -- "(^|[[:space:],])${flag}([[:space:],=]|$)" <<<"$out"; then
    ok "$bin $sub $flag"
  else
    bad "$bin $sub $flag — không thấy trong --help"
  fi
}

echo "=== Preflight · đối chiếu CLI thật với những gì repo giả định ==="

hdr "Phiên bản đã cài"
for b in node python3 docker acpx mcporter openclaw clawhub yq opa gh; do
  if have "$b"; then
    printf '  %-10s %s\n' "$b" "$("$b" --version 2>&1 | head -1)"
  else
    printf '  %-10s %s\n' "$b" "${C_WARN}chưa cài${C_OFF}"
  fi
done

hdr "mcporter — tầng năng lực"
check_sub  mcporter list
check_sub  mcporter call
check_sub  mcporter serve
check_sub  mcporter daemon
check_sub  mcporter generate-cli
check_flag mcporter serve "--http"
check_flag mcporter serve "--servers"
if have mcporter; then
  if mcporter serve --help 2>&1 | grep -qE -- '--host|--bind'; then
    ok "mcporter serve có cờ đổi địa chỉ nghe → bridge-up.sh dùng trực tiếp"
  else
    echo "${C_WARN}!${C_OFF} mcporter serve chỉ nghe loopback → bridge-up.sh sẽ dùng socat chuyển tiếp"
    have socat || echo "     ${C_WARN}cần cài socat trong ảnh agent-runner${C_OFF}"
  fi
  echo "${C_DIM}  Cú pháp gọi tool (đối chiếu với dept-request.flow.ts):${C_OFF}"
  mcporter call --help 2>&1 | sed -n '1,12p' | sed 's/^/     /'
fi

hdr "acpx — tầng thực thi"
check_sub  acpx exec
check_sub  acpx sessions
check_sub  acpx flow
check_flag acpx exec "--cwd"
check_flag acpx exec "--format"
check_flag acpx exec "--deny-all"
check_flag acpx exec "--approve-all"
check_flag acpx exec "--json-strict"
check_flag acpx exec "--suppress-reads"

hdr "openclaw — tầng điều khiển"
check_sub openclaw agents
check_sub openclaw skills
check_sub openclaw config
check_sub openclaw security

hdr "clawhub — tầng phân phối"
check_sub clawhub skill
check_sub clawhub login

hdr "Môi trường"
if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "${C_WARN}!${C_OFF} Đang chạy trong WSL."
  case "$PWD" in
    /mnt/*)
      bad "Repo nằm trên ổ Windows ($PWD)."
      cat <<'WSL'
     Hai hệ quả thật, không phải lý thuyết:
       1. chmod không bám trên /mnt/c (trừ khi bật metadata) → script mất quyền
          chạy, và .env không giữ được quyền 600.
       2. I/O chậm hơn nhiều lần; docker build và npm install sẽ ì.
     Cách sửa:
       cp -r "$PWD" ~/agent-fleet && cd ~/agent-fleet && chmod +x $(find . -name '*.sh')
WSL
      ;;
    *) ok "Repo nằm trên filesystem Linux — đúng chỗ" ;;
  esac
fi

if [[ -f .env ]]; then
  perm="$(stat -c '%a' .env 2>/dev/null || echo '?')"
  [[ "$perm" == "600" ]] && ok ".env quyền 600" || echo "${C_WARN}!${C_OFF} .env đang quyền $perm (nên là 600)"
fi

echo
if (( MISS )); then
  echo "${C_ERR}CẦN SỬA:${C_OFF} có lệnh/cờ repo giả định nhưng bản CLI đã cài không có."
  echo "Gửi lại toàn bộ đầu ra của script này để tôi chỉnh đúng cho phiên bản của bạn."
  exit 1
fi
echo "${C_OK}Khớp hết — CLI trên máy bạn đúng như repo giả định.${C_OFF}"
