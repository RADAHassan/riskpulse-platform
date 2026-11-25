package com.fintech.customer.dto;

import com.fintech.customer.domain.CustomerStatus;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CustomerStatusRequest(
        @NotNull CustomerStatus status,
        @Size(max = 255) String reason) {

    public CustomerStatusRequest {
        reason = DtoRules.clean(reason);
    }
}