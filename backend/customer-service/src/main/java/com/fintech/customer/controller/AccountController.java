package com.fintech.customer.controller;

import com.fintech.customer.dto.AccountResponse;
import com.fintech.customer.dto.AccountStatusRequest;
import com.fintech.customer.dto.OpenAccountRequest;
import com.fintech.customer.dto.PageResponse;
import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import com.fintech.customer.security.CurrentUser;
import com.fintech.customer.security.Role;
import com.fintech.customer.service.AccountService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
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
import java.net.URI;
import java.util.Set;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
@Tag(name = "Accounts", description = "Comptes (C-07 a C-10)")
@SecurityRequirement(name = "userId")
@SecurityRequirement(name = "userRole")
@SecurityRequirement(name = "userEmail")
public class AccountController {

    private static final Set<String> SORTABLE = Set.of("openedAt", "balance");

    private final AccountService accountService;
    @Operation(summary = "C-07 Ouvrir un compte", description = "Role : CLIENT. Solde initial 0 ; decouvert, taux et minimum fixes par la banque.")
    @ApiResponse(responseCode = "201", description = "Compte cree")
    @ApiResponse(responseCode = "422", description = "PROFILE_REQUIRED ou CUSTOMER_NOT_ACTIVE")
    @PostMapping("/customers/me/accounts")
    public ResponseEntity<AccountResponse> open(CurrentUser user, @Valid @RequestBody OpenAccountRequest request) {
        user.requireRole(Role.CLIENT);
        AccountResponse created = accountService.open(user.id(), request);
        return ResponseEntity.created(URI.create("/api/v1/accounts/" + created.id())).body(created);
    }
    @Operation(summary = "C-08 Lister ses comptes", description = "Role : CLIENT")
    @GetMapping("/customers/me/accounts")
    public PageResponse<AccountResponse> listMine(CurrentUser user,
                                                  @RequestParam(defaultValue = "0") int page,
                                                  @RequestParam(defaultValue = "20") int size,
                                                  @RequestParam(required = false) String sort) {
        user.requireRole(Role.CLIENT);
        return accountService.listMine(user.id(),
                PageRequests.of(page, size, sort, SORTABLE, "openedAt", Sort.Direction.DESC));
    }
    @Operation(summary = "C-09 Detail d'un compte", description = "CLIENT proprietaire ou ANALYST. Compte d'autrui : 404 ACCOUNT_NOT_FOUND.")
    @GetMapping("/accounts/{id}")
    public AccountResponse get(CurrentUser user, @PathVariable UUID id) {
        return switch (user.role()) {
            case CLIENT -> accountService.getForClient(user.id(), id);
            case ANALYST -> accountService.getForStaff(id);
            case ADMIN -> throw new BusinessRuleException(ErrorCode.FORBIDDEN, "Insufficient role");
        };
    }
    @Operation(summary = "C-10 Geler, degeler, cloturer", description = "ANALYST : geler seulement. ADMIN : tout.")
    @ApiResponse(responseCode = "422", description = "INVALID_STATE_TRANSITION ou BUSINESS_RULE_VIOLATION")
    @PatchMapping("/accounts/{id}/status")
    public AccountResponse changeStatus(CurrentUser user, @PathVariable UUID id,
                                        @Valid @RequestBody AccountStatusRequest request) {
        user.requireRole(Role.ANALYST, Role.ADMIN);
        return accountService.changeStatus(id, request, user.role());
    }
}