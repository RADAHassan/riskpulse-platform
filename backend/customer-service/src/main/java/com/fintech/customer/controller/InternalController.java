package com.fintech.customer.controller;

import com.fintech.customer.dto.InternalAccountResponse;
import com.fintech.customer.dto.MovementRequest;
import com.fintech.customer.dto.MovementResponse;
import com.fintech.customer.service.InternalAccountService;
import com.fintech.customer.service.MovementService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;

/** Endpoints internes : jamais routes par le Gateway, proteges par ServiceTokenFilter. */
@RestController
@RequestMapping("/internal")
@RequiredArgsConstructor
@Tag(name = "Internal", description = "Appels entre services (I-01, I-02). Jamais exposes par le Gateway.")
@SecurityRequirement(name = "serviceToken")
public class InternalController {

    private final InternalAccountService accountService;
    private final MovementService movementService;

    /** I-01 par identifiant. */
    @Operation(summary = "I-01 Consulter un compte", description = "Appelant : transaction-service")
    @GetMapping("/accounts/{id}")
    public InternalAccountResponse getAccount(@PathVariable UUID id) {
        return accountService.getById(id);
    }

    /** I-01 par numero : GET /internal/accounts?accountNumber=... */
    @Operation(summary = "I-02 Appliquer un mouvement (idempotent)", description = "DEBIT, CREDIT ou TRANSFER atomique. Rejeu avec le meme transactionId : ALREADY_APPLIED.")
    @ApiResponse(responseCode = "409", description = "IDEMPOTENCY_KEY_REUSED")
    @ApiResponse(responseCode = "422", description = "INSUFFICIENT_FUNDS, ACCOUNT_FROZEN, ACCOUNT_CLOSED, CURRENCY_MISMATCH, SAME_ACCOUNT_TRANSFER")
    @GetMapping("/accounts")
    public InternalAccountResponse getAccountByNumber(@RequestParam String accountNumber) {
        return accountService.getByNumber(accountNumber);
    }

    /** I-02. */
    @PostMapping("/accounts/movements")
    public MovementResponse movement(@Valid @RequestBody MovementRequest request) {
        return movementService.apply(request);
    }
}