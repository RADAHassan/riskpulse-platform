package com.riskpulse.common.security;

import java.util.List;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

/**
 * The caller as described by the validated JWT. Used for ownership checks (BOLA / IDOR protection):
 * staff roles see everything, a CUSTOMER only the resources of the {@code customer_id} claim.
 */
public record AuthenticatedUser(UUID userId, String username, String role, UUID customerId) {

    public static final String CLAIM_ROLES = "roles";
    public static final String CLAIM_CUSTOMER_ID = "customer_id";
    public static final String CLAIM_USERNAME = "username";

    public static AuthenticatedUser from(Jwt jwt) {
        List<String> roles = jwt.getClaimAsStringList(CLAIM_ROLES);
        String role = roles == null || roles.isEmpty() ? "" : roles.get(0);
        String customer = jwt.getClaimAsString(CLAIM_CUSTOMER_ID);
        return new AuthenticatedUser(
                parseUuid(jwt.getSubject()),
                jwt.getClaimAsString(CLAIM_USERNAME),
                role,
                parseUuid(customer));
    }

    public static AuthenticatedUser from(Authentication authentication) {
        if (authentication instanceof JwtAuthenticationToken token) {
            return from(token.getToken());
        }
        throw new IllegalStateException("No JWT authentication in the security context");
    }

    public boolean isStaff() {
        return Roles.ADMIN.equals(role) || Roles.ANALYST.equals(role);
    }

    public boolean isAdmin() {
        return Roles.ADMIN.equals(role);
    }

    /** BOLA rule: staff may access any customer; a CUSTOMER only the customer bound to the token. */
    public boolean canAccessCustomer(UUID customer) {
        return isStaff() || (customer != null && customer.equals(customerId));
    }

    private static UUID parseUuid(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return UUID.fromString(value);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }
}
