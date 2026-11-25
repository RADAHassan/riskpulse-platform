package com.fintech.customer.dto.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

import java.time.LocalDate;
import java.time.ZoneOffset;

public class AdultValidator implements ConstraintValidator<Adult, LocalDate> {

    private int minAge;

    @Override
    public void initialize(Adult annotation) {
        this.minAge = annotation.minAge();
    }

    @Override
    public boolean isValid(LocalDate birthDate, ConstraintValidatorContext context) {
        if (birthDate == null) {
            return true; // l'absence de valeur est le travail de @NotNull
        }
        return !birthDate.isAfter(LocalDate.now(ZoneOffset.UTC).minusYears(minAge));
    }
}