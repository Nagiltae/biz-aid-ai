/** FastAPI 연결 전 상태 안내. 가짜 결과 대신 지금 무엇이 되고 무엇이 준비 중인지 정직하게 보여 준다. */
export function AiNotConnectedNotice({ what }: { what: string }) {
  return (
    <div className="alert info" role="status">
      <strong>AI 연결 준비 중</strong>
      <span>
        {what}은(는) AI 서비스 연결 작업이 끝나면 이 화면에서 바로 볼 수 있습니다. 지금은 요청이 서비스 서버까지 정상 전달되는 것만 확인됩니다.
      </span>
    </div>
  );
}
