package com.fintech.customer.dto;
import java.math.BigDecimal;
import java.math.RoundingMode;
/** Règles partagées par plusieurs DTO (visibilité package : usage interne). */
final class DtoRules {

    /** Format international : +212612345678 (contrat, section 4.4). */
    static final String PHONE = "^\\+[1-9]\\d{7,14}$";

    private DtoRules() {
    }

    /** Contrat section 4.1 : espaces de début et de fin supprimés. */
    static String clean(String value) {
        return value == null ? null : value.strip();
    }
    /** Contrat section 4.1 : montants a 2 decimales en sortie. */
    static BigDecimal money(BigDecimal value) {
        return value == null ? null : value.setScale(2, RoundingMode.HALF_EVEN);
    }
}