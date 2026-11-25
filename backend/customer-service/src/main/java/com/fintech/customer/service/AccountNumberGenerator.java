package com.fintech.customer.service;

import org.springframework.stereotype.Component;

import java.security.SecureRandom;

/** Numero de compte : "MA" + 22 chiffres aleatoires. L'unicite finale est garantie par la contrainte UNIQUE en base. */
@Component
public class AccountNumberGenerator {

    private static final String PREFIX = "MA";
    private static final int DIGITS = 22;

    private final SecureRandom random = new SecureRandom();

    public String next() {
        StringBuilder number = new StringBuilder(PREFIX);
        for (int i = 0; i < DIGITS; i++) {
            number.append(random.nextInt(10));
        }
        return number.toString();
    }
}
