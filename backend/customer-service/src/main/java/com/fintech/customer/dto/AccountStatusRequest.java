package com.fintech.customer.dto;

import com.fintech.customer.domain.AccountStatus;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record AccountStatusRequest(
        @NotNull AccountStatus status,
        @NotBlank @Size(min = 5, max = 255) String reason) {

    public AccountStatusRequest {
        reason = DtoRules.clean(reason);
    }
}