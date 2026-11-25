package com.fintech.customer.dto;

import com.fintech.customer.dto.validation.Adult;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Past;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.LocalDate;

/** userId et email ne sont PAS ici : ils viennent du jeton (hypothese H2). */
public record CreateCustomerRequest(
        @NotBlank @Size(max = 100) String firstName,
        @NotBlank @Size(max = 100) String lastName,
        @NotBlank @Pattern(regexp = DtoRules.PHONE, message = "must be in international format, e.g. +212612345678")
        String phone,
        @NotNull @Past @Adult LocalDate birthDate,
        @NotBlank @Size(max = 255) String address) {

    public CreateCustomerRequest {
        firstName = DtoRules.clean(firstName);
        lastName = DtoRules.clean(lastName);
        phone = DtoRules.clean(phone);
        address = DtoRules.clean(address);
    }
}