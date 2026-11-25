package com.fintech.customer.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record UpdateContactRequest(
        @NotBlank @Pattern(regexp = DtoRules.PHONE, message = "must be in international format, e.g. +212612345678")
        String phone,
        @NotBlank @Size(max = 255) String address) {

    public UpdateContactRequest {
        phone = DtoRules.clean(phone);
        address = DtoRules.clean(address);
    }
}