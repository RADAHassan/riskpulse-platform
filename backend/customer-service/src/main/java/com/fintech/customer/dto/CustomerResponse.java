package com.fintech.customer.dto;

import com.fintech.customer.domain.CustomerStatus;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public record CustomerResponse(
        UUID userId,
        String firstName,
        String lastName,
        String email,
        String phone,
        LocalDate birthDate,
        String address,
        CustomerStatus status,
        Instant createdAt,
        Instant updatedAt) {
}