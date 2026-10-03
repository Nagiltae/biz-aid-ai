package com.bizaid.activity.domain;

/** 기록하는 사용자 활동 종류. 운영 확인(누가 언제 무엇을 했고 성공했는지)에 필요한 V1 핵심 흐름만 둔다. */
public enum ActivityAction {
    SIGNUP,
    LOGIN,
    LOGOUT,
    ACCOUNT_DELETE,
    PASSWORD_CHANGE,
    COMPANY_CREATE,
    COMPANY_UPDATE,
    CONVERSATION_CREATE,
    CONVERSATION_DELETE,
    AI_QUERY,
    ELIGIBILITY_CHECK
}
