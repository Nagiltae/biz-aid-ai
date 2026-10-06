#!/usr/bin/env bash
# 운영 점검(cron 10분마다): 컨테이너·디스크·메모리·FastAPI 상태·AI 실패·backend 오류를 보고 문제가 있으면 SNS 메일을 보낸다.
# BOUNDARY: 비밀값(.env.prod)·DB를 읽지 않는다. 로그는 줄 수만 세고 내용(사용자 질문·IP·경로)을 출력·전송하지 않는다.
# 사용법: monitor_prod.sh [--dry-run | --test]
#   --dry-run  메일을 보내지 않고 점검 결과와 보낼 메일 내용만 화면에 출력(상태 파일도 바꾸지 않음)
#   --test     설정 확인용 테스트 메일 1통만 보낸다
# 설정 파일(기본 ~/bizaid/monitor.conf, BIZAID_MONITOR_CONF로 변경): KEY=VALUE 줄만 읽는다.
#   SNS_TOPIC_ARN=arn:aws:sns:...   (필수, --dry-run은 없어도 됨)
#   선택(기본값): SNS_REGION=ap-southeast-2, COMPOSE_PROJECT=biz-aid-prod
#   선택 기준(기본값): DISK_PERCENT=80, MEMORY_PERCENT=90, AI_FAILURES=3, BACKEND_ERRORS=10, WINDOW=10m, REPEAT_SECONDS=3600
set -uo pipefail
# WHY: cron의 PATH에는 /usr/local/bin(aws CLI)이 없을 수 있다. 기존 PATH 뒤에 붙여 사용자가 고른 명령을 우선한다.
export PATH="${PATH:-/usr/bin:/bin}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

MODE=run
case "${1:-}" in
  "") ;;
  --dry-run) MODE=dry ;;
  --test) MODE=test ;;
  *) echo "사용법: monitor_prod.sh [--dry-run | --test]" >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { echo "사용법: monitor_prod.sh [--dry-run | --test]" >&2; exit 2; }

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CONF="${BIZAID_MONITOR_CONF:-$ROOT/monitor.conf}"
STATE="${BIZAID_MONITOR_STATE:-$ROOT/.monitor-state}"
SERVICES="caddy frontend backend fastapi qdrant"
MEMINFO="${BIZAID_MONITOR_MEMINFO:-/proc/meminfo}"

SNS_TOPIC_ARN="" SNS_REGION="ap-southeast-2" COMPOSE_PROJECT="biz-aid-prod"
DISK_PERCENT=80 MEMORY_PERCENT=90 AI_FAILURES=3 BACKEND_ERRORS=10 WINDOW=10m REPEAT_SECONDS=3600

# BOUNDARY: 설정 파일을 셸로 실행(source)하지 않고 허용한 이름의 KEY=VALUE만 읽는다.
read_conf() {
  local line key value
  [[ -f "$CONF" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    [[ "$line" == *=* ]] || continue
    key="$(echo "${line%%=*}" | tr -d '[:space:]')"
    value="$(echo "${line#*=}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/')"
    case "$key" in
      SNS_TOPIC_ARN|SNS_REGION|COMPOSE_PROJECT|WINDOW) printf -v "$key" '%s' "$value" ;;
      DISK_PERCENT|MEMORY_PERCENT|AI_FAILURES|BACKEND_ERRORS|REPEAT_SECONDS)
        [[ "$value" =~ ^[0-9]+$ ]] || { echo "FAIL: 설정 $key 는 숫자여야 합니다." >&2; exit 1; }
        printf -v "$key" '%s' "$value" ;;
    esac
  done < "$CONF"
}
read_conf
[[ "$WINDOW" =~ ^[0-9]+[mh]$ ]] || { echo "FAIL: WINDOW는 10m 같은 형식이어야 합니다." >&2; exit 1; }

HOST="$(hostname 2>/dev/null || echo unknown)"
NOW="$(date +%s)"
STAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"

publish() {  # $1 제목(ASCII), $2 본문
  if [[ "$MODE" == dry ]]; then
    printf -- '--- [dry-run] 보낼 메일 ---\n제목: %s\n%s\n---------------------------\n' "$1" "$2"
    return 0
  fi
  [[ -n "$SNS_TOPIC_ARN" ]] || { echo "FAIL: $CONF 에 SNS_TOPIC_ARN이 없습니다." >&2; return 1; }
  command -v aws >/dev/null 2>&1 || { echo "FAIL: aws CLI가 없습니다." >&2; return 1; }
  # RISK: aws 오류 원문에는 계정 정보가 섞일 수 있어 화면에 내지 않고 실패 여부만 남긴다.
  if aws sns publish --region "$SNS_REGION" --topic-arn "$SNS_TOPIC_ARN" --subject "$1" --message "$2" >/dev/null 2>&1; then
    return 0
  fi
  echo "FAIL: SNS 메일 전송 실패(서버 IAM 역할의 sns:Publish 권한·주제 ARN·지역을 확인하세요)." >&2
  return 1
}

if [[ "$MODE" == test ]]; then
  publish "[BizAid] TEST monitor mail from $HOST" "BizAid 운영 점검 테스트 메일입니다.
서버: $HOST
시각: $STAMP
이 메일이 왔다면 cron 점검의 알림 경로(SNS)가 정상입니다." || exit 1
  echo "OK: 테스트 메일을 보냈습니다. 메일함(스팸함 포함)을 확인하세요."
  exit 0
fi

command -v docker >/dev/null 2>&1 || { echo "FAIL: docker 명령이 없습니다." >&2; exit 1; }

# BOUNDARY: compose 설정·운영 비밀값 파일을 읽지 않고 compose label로 서비스 컨테이너를 찾는다.
container() {  # 서비스 이름 → 실행 중 컨테이너 ID(없으면 빈 값)
  docker ps -q --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
    --filter "label=com.docker.compose.service=$1" --filter status=running 2>/dev/null | head -n 1
}

ISSUES=()   # "key|설명|확인 명령"
OK_LINES=()
add_issue() { ISSUES+=("$1|$2|$3"); }

# 1) 컨테이너 5개 running
for service in $SERVICES; do
  if [[ -z "$(container "$service")" ]]; then
    add_issue "container_$service" "컨테이너 $service 가 실행 중이 아닙니다" "docker compose -p $COMPOSE_PROJECT ps -a $service"
  fi
done
[[ ${#ISSUES[@]} -eq 0 ]] && OK_LINES+=("컨테이너 5개 running")

# 2) 디스크(루트 파일시스템)
disk="$(df -P / 2>/dev/null | awk 'NR==2 {gsub("%","",$5); print $5}')"
if [[ "$disk" =~ ^[0-9]+$ ]]; then
  if (( disk >= DISK_PERCENT )); then
    add_issue disk "디스크 사용률 ${disk}% (기준 ${DISK_PERCENT}%)" "df -h / && docker system df"
  else
    OK_LINES+=("디스크 ${disk}%")
  fi
else
  OK_LINES+=("디스크 확인 불가(건너뜀)")
fi

# 3) 메모리(Linux /proc/meminfo, 사용 가능 메모리 기준). macOS dev에는 없어서 건너뛴다.
if [[ -r "$MEMINFO" ]]; then
  memory="$(awk '/^MemTotal:/ {t=$2} /^MemAvailable:/ {a=$2} END {if (t>0) printf "%d", (t-a)*100/t}' "$MEMINFO")"
  if [[ "$memory" =~ ^[0-9]+$ ]] && (( memory >= MEMORY_PERCENT )); then
    add_issue memory "메모리 사용률 ${memory}% (기준 ${MEMORY_PERCENT}%)" "free -h && docker stats --no-stream"
  else
    OK_LINES+=("메모리 ${memory:-?}%")
  fi
else
  OK_LINES+=("메모리 확인 불가(/proc/meminfo 없음, 건너뜀)")
fi

# 4) FastAPI 상태 확인. 외부에 공개되지 않으므로 컨테이너 안에서 /health를 부른다(deploy.sh와 같은 방법).
fastapi="$(container fastapi)"
if [[ -n "$fastapi" ]]; then
  if docker exec "$fastapi" python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=5).close()" >/dev/null 2>&1; then
    OK_LINES+=("FastAPI /health 응답")
  else
    add_issue fastapi_health "FastAPI가 내부 상태 확인(/health)에 응답하지 않습니다" "docker compose -p $COMPOSE_PROJECT logs --since 10m fastapi | tail -n 50"
  fi
fi

# 5·6) 최근 로그 줄 수. 줄 내용은 내보내지 않고 개수만 쓴다.
count_lines() {  # $1 컨테이너, $2 정규식
  [[ -n "$1" ]] || { echo 0; return; }
  docker logs --since "$WINDOW" "$1" 2>&1 | grep -cE "$2" || true
}
backend="$(container backend)"
# WHY: FastAPI는 Bedrock 시간 초과를 로그로 남기지 않고 503 코드로만 돌려준다. backend가 그 503(시간 초과·호출 실패·의존 서비스 불가)과
# 자기 90초 시간 초과를 WARN 한 줄씩 남기므로 이것을 센다. FastAPI의 "Bedrock invocation failed"는 같은 실패의 다른 기록일 수 있어
# 더하지 않고 둘 중 큰 값을 쓴다(맞춤 추천 안 공고별 판정 실패는 HTTP 200이라 backend에 남지 않으므로 FastAPI 쪽 수가 필요하다).
backend_ai="$(count_lines "$backend" 'AI upstream error path=[^ ]+ status=50[34]|AI upstream io failure path=[^ ]+ type=Http(Connect)?TimeoutException')"
fastapi_ai="$(count_lines "$fastapi" 'Bedrock invocation failed')"
ai_failures=$(( backend_ai > fastapi_ai ? backend_ai : fastapi_ai ))
if (( ai_failures >= AI_FAILURES )); then
  add_issue ai_failures "최근 $WINDOW AI(Bedrock) 호출 실패·시간 초과 ${ai_failures}건 (기준 ${AI_FAILURES}건; backend ${backend_ai}, fastapi ${fastapi_ai})" \
    "docker compose -p $COMPOSE_PROJECT logs --since $WINDOW backend fastapi | grep -E 'AI upstream|Bedrock invocation failed' | tail -n 20"
else
  OK_LINES+=("AI 실패 ${ai_failures}건")
fi
# Spring 기본 로그 형식의 ERROR 줄(예상 못 한 500 오류는 GlobalExceptionHandler가 ERROR로 남긴다). stack trace 줄은 세지 않는다.
backend_errors="$(count_lines "$backend" '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[^ ]+ +ERROR ')"
if (( backend_errors >= BACKEND_ERRORS )); then
  add_issue backend_errors "최근 $WINDOW backend ERROR 로그 ${backend_errors}건 (기준 ${BACKEND_ERRORS}건)" \
    "docker compose -p $COMPOSE_PROJECT logs --since $WINDOW backend | grep -E ' ERROR ' | cut -c1-160 | tail -n 20"
else
  OK_LINES+=("backend ERROR ${backend_errors}건")
fi

# 알림: 문제마다 상태 파일(<key>.sent = 마지막 전송 시각)로 1시간에 1번만 보낸다. 사라진 문제는 해결 메일 1통 후 파일을 지운다.
[[ "$MODE" == dry ]] || mkdir -p "$STATE" || { echo "FAIL: 상태 폴더를 만들 수 없습니다: $STATE" >&2; exit 1; }
# WHY: cron이 겹쳐 실행돼도 같은 메일을 두 번 보내지 않게 잠근다(30분 넘은 잠금은 비정상 종료로 보고 정리).
if [[ "$MODE" != dry ]]; then
  find "$STATE" -maxdepth 1 -name lock -type d -mmin +30 -exec rmdir {} + 2>/dev/null
  mkdir "$STATE/lock" 2>/dev/null || { echo "SKIP: 이전 점검이 아직 실행 중입니다."; exit 0; }
  trap 'rmdir "$STATE/lock" 2>/dev/null' EXIT
fi

due=() active_keys=" "
for issue in ${ISSUES[@]+"${ISSUES[@]}"}; do
  key="${issue%%|*}"
  active_keys+="$key "
  last="$(cat "$STATE/$key.sent" 2>/dev/null || echo 0)"
  [[ "$last" =~ ^[0-9]+$ ]] || last=0
  (( NOW - last >= REPEAT_SECONDS )) && due+=("$issue")
done
resolved=()
for file in "$STATE"/*.sent; do
  [[ -e "$file" ]] || continue
  key="$(basename "$file" .sent)"
  [[ "$active_keys" == *" $key "* ]] || resolved+=("$key")
done

echo "[$STAMP] 문제 ${#ISSUES[@]}건, 이번에 알릴 문제 ${#due[@]}건, 해결 ${#resolved[@]}건. 정상: $(IFS=', '; echo "${OK_LINES[*]:-없음}")"
for issue in ${ISSUES[@]+"${ISSUES[@]}"}; do
  rest="${issue#*|}"
  echo "  문제: ${rest%%|*}"
done

status=0
if (( ${#due[@]} > 0 )); then
  body="BizAid 운영 점검에서 문제를 찾았습니다.
서버: $HOST
시각: $STAMP
"
  for issue in "${due[@]}"; do
    rest="${issue#*|}"
    body+="
- ${rest%%|*}
  확인: ${rest#*|}"
  done
  body+="

같은 문제는 1시간에 1번만 다시 알립니다. 해결되면 해결 메일이 갑니다.
서버 위치: cd $ROOT"
  if publish "[BizAid] ALERT ${#due[@]} issue(s) on $HOST" "$body"; then
    if [[ "$MODE" != dry ]]; then
      for issue in "${due[@]}"; do echo "$NOW" > "$STATE/${issue%%|*}.sent"; done
    fi
  else
    status=1   # 상태를 바꾸지 않아 다음 실행에서 다시 보낸다.
  fi
fi
if (( ${#resolved[@]} > 0 )); then
  body="BizAid 운영 점검에서 이전에 알린 문제가 해결됐습니다.
서버: $HOST
시각: $STAMP
"
  for key in "${resolved[@]}"; do body+="
- 해결: $key"; done
  if publish "[BizAid] RESOLVED ${#resolved[@]} issue(s) on $HOST" "$body"; then
    if [[ "$MODE" != dry ]]; then
      for key in "${resolved[@]}"; do rm -f "$STATE/$key.sent"; done
    fi
  else
    status=1
  fi
fi
exit "$status"
