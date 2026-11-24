package com.riskpulse.common.security;

/** Role names carried in the {@code roles} claim of the access token (without the ROLE_ prefix). */
public final class Roles {

    public static final String ADMIN = "ADMIN";
    public static final String ANALYST = "ANALYST";
    public static final String CUSTOMER = "CUSTOMER";

    private Roles() {
    }
}
