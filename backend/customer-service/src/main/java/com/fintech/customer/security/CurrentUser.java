package com.fintech.customer.security;

import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;

import java.util.Arrays;
import java.util.UUID;

public record CurrentUser(UUID id, Role role, String email) {

    public void requireRole(Role... allowed) {
        if (!Arrays.asList(allowed).contains(role)) {
            throw new BusinessRuleException(ErrorCode.FORBIDDEN, "Insufficient role");
        }
    }
}