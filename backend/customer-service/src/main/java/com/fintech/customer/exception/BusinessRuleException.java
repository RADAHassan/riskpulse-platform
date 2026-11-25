package com.fintech.customer.exception;

/**
 * Levee quand une regle metier est violee. Le code determine la reponse HTTP (etape 6).
 * RuntimeException : Spring annule automatiquement la transaction en cours.
 */
public class BusinessRuleException extends RuntimeException {

    private final ErrorCode code;

    public BusinessRuleException(String message) {
        this(ErrorCode.BUSINESS_RULE_VIOLATION, message);
    }

    public BusinessRuleException(ErrorCode code, String message) {
        super(message);
        this.code = code;
    }

    public ErrorCode getCode() {
        return code;
    }
}