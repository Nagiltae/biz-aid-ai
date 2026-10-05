#!/usr/bin/env bash
# 공고 영역만 이사한다. 회원·대화·활동·체험·Flyway history는 이 덤프에 포함하지 않는다.
set -euo pipefail
if [[ $# != 2 ]]; then
  echo '사용법: export_program_data.sh <원본 MySQL 컨테이너> <새 출력.sql>' >&2
  exit 2
fi
[[ ! -e "$2" ]] || { echo '기존 덤프는 덮어쓰지 않습니다.' >&2; exit 1; }
# 비밀번호는 컨테이너 내부 process에서만 사용한다. command line과 출력에는 포함하지 않는다.
docker exec "$1" sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysqldump -u "$MYSQL_USER" --hex-blob --single-transaction --no-tablespaces --set-gtid-purged=OFF --no-create-info --skip-add-locks --skip-disable-keys --skip-comments --complete-insert "$MYSQL_DATABASE" support_programs support_program_sync_history document_acquisition_runs document_sources document_parse_results document_archive_members' > "$2"
echo '공고 데이터 덤프 완료(개인정보 영역 제외).'
