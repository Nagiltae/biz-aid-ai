package com.bizaid.auth.domain;

/** 계정 종류. TRIAL은 "체험하기"로 만든 임시 계정이며 생성 24시간 뒤 정리 작업이 데이터와 함께 지운다. */
public enum AccountType {
    MEMBER,
    TRIAL
}
