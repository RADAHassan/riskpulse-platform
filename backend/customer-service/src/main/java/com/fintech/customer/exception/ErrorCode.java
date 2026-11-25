package com.fintech.customer.exception;

public enum ErrorCode {
    VALIDATION_ERROR(400),
    UNAUTHENTICATED(401),
    FORBIDDEN(403),
    NOT_FOUND(404),
    ACCOUNT_NOT_FOUND(404),
    PROFILE_ALREADY_EXISTS(409),
    EMAIL_ALREADY_USED(409),
    CONFLICT(409),
    PROFILE_REQUIRED(422),
    CUSTOMER_NOT_ACTIVE(422),
    ACCOUNT_FROZEN(422),
    ACCOUNT_CLOSED(422),
    INSUFFICIENT_FUNDS(422),
    INVALID_STATE_TRANSITION(422),
    BUSINESS_RULE_VIOLATION(422),
    CURRENCY_MISMATCH(422),
    SAME_ACCOUNT_TRANSFER(422),
    IDEMPOTENCY_KEY_REUSED(409),
    INTERNAL_ERROR(500);
    private final int httpStatus;

    ErrorCode(int httpStatus) {
        this.httpStatus = httpStatus;
    }

    public int getHttpStatus() {
        return httpStatus;
    }
}