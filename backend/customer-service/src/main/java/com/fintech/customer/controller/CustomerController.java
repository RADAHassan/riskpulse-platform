package com.fintech.customer.controller;

import com.fintech.customer.domain.CustomerStatus;
import com.fintech.customer.dto.CreateCustomerRequest;
import com.fintech.customer.dto.CustomerResponse;
import com.fintech.customer.dto.CustomerStatusRequest;
import com.fintech.customer.dto.PageResponse;
import com.fintech.customer.dto.UpdateContactRequest;
import com.fintech.customer.security.CurrentUser;
import com.fintech.customer.security.Role;
import com.fintech.customer.service.CustomerService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Sort;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
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
@RequestMapping("/api/v1/customers")
@RequiredArgsConstructor
@Tag(name = "Customers", description = "Profils clients (C-01 a C-06)")
@SecurityRequirement(name = "userId")
@SecurityRequirement(name = "userRole")
@SecurityRequirement(name = "userEmail")
public class CustomerController {

    private static final Set<String> SORTABLE = Set.of("createdAt", "lastName");

    private final CustomerService customerService;
    @Operation(summary = "C-01 Creer son profil", description = "Role : CLIENT sans profil. userId et email viennent de l'identite, jamais du corps.")
    @ApiResponse(responseCode = "201", description = "Profil cree (en-tete Location)")
    @ApiResponse(responseCode = "400", description = "VALIDATION_ERROR")
    @ApiResponse(responseCode = "403", description = "FORBIDDEN")
    @ApiResponse(responseCode = "409", description = "PROFILE_ALREADY_EXISTS ou EMAIL_ALREADY_USED")
    @PostMapping
    public ResponseEntity<CustomerResponse> create(CurrentUser user,
                                                   @Valid @RequestBody CreateCustomerRequest request) {
        user.requireRole(Role.CLIENT);
        CustomerResponse created = customerService.create(user.id(), user.email(), request);
        return ResponseEntity.created(URI.create("/api/v1/customers/me")).body(created);
    }
    @Operation(summary = "C-02 Consulter son profil", description = "Role : CLIENT")
    @GetMapping("/me")
    public CustomerResponse me(CurrentUser user) {
        user.requireRole(Role.CLIENT);
        return customerService.get(user.id());
    }
    @Operation(summary = "C-03 Modifier telephone et adresse", description = "Role : CLIENT")
    @PutMapping("/me")
    public CustomerResponse updateMe(CurrentUser user, @Valid @RequestBody UpdateContactRequest request) {
        user.requireRole(Role.CLIENT);
        return customerService.updateContact(user.id(), request);
    }
    @Operation(summary = "C-04 Lister les profils", description = "Roles : ADMIN, ANALYST. Pagination : page, size (max 100), sort.")
    @GetMapping
    public PageResponse<CustomerResponse> list(CurrentUser user,
                                               @RequestParam(required = false) CustomerStatus status,
                                               @RequestParam(defaultValue = "0") int page,
                                               @RequestParam(defaultValue = "20") int size,
                                               @RequestParam(required = false) String sort) {
        user.requireRole(Role.ADMIN, Role.ANALYST);
        return customerService.list(status,
                PageRequests.of(page, size, sort, SORTABLE, "createdAt", Sort.Direction.DESC));
    }
    @Operation(summary = "C-05 Consulter un profil", description = "Roles : ADMIN, ANALYST")
    @GetMapping("/{userId}")
    public CustomerResponse get(CurrentUser user, @PathVariable UUID userId) {
        user.requireRole(Role.ADMIN, Role.ANALYST);
        return customerService.get(userId);
    }
    @Operation(summary = "C-06 Suspendre, reactiver ou cloturer", description = "Role : ADMIN")
    @ApiResponse(responseCode = "422", description = "INVALID_STATE_TRANSITION ou BUSINESS_RULE_VIOLATION")
    @PatchMapping("/{userId}/status")
    public CustomerResponse changeStatus(CurrentUser user, @PathVariable UUID userId,
                                         @Valid @RequestBody CustomerStatusRequest request) {
        user.requireRole(Role.ADMIN);
        return customerService.changeStatus(userId, request);
    }

}