package com.riskpulse.customer;

import com.riskpulse.common.audit.AuditClient;
import com.riskpulse.common.audit.AuditEvent;
import com.riskpulse.common.security.AuthenticatedUser;
import com.riskpulse.common.web.ApiException;
import com.riskpulse.common.web.PageResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Customer API. Authorisation = role (method security) AND ownership: a CUSTOMER token only ever reaches the
 * customer bound to its {@code customer_id} claim (BOLA/IDOR protection, OWASP API1).
 */
@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    public record CustomerRequest(
            @NotBlank @Size(max = 100) String firstName,
            @NotBlank @Size(max = 100) String lastName,
            @NotBlank @Email @Size(max = 254) String email,
            @NotBlank @Pattern(regexp = "^[A-Z]{2}$", message = "must be an ISO 3166-1 alpha-2 code") String country,
            Customer.Segment segment) {
    }

    public record CustomerUpdate(
            @NotBlank @Size(max = 100) String firstName,
            @NotBlank @Size(max = 100) String lastName,
            @NotBlank @Pattern(regexp = "^[A-Z]{2}$") String country) {
    }

    public record CustomerResponse(UUID id, String firstName, String lastName, String email, String country,
                                   Customer.Segment segment, Instant createdAt) {
        static CustomerResponse of(Customer c) {
            return new CustomerResponse(c.getId(), c.getFirstName(), c.getLastName(), c.getEmail(), c.getCountry(),
                    c.getSegment(), c.getCreatedAt());
        }
    }

    private final CustomerRepository repository;
    private final AuditClient audit;

    public CustomerController(CustomerRepository repository, AuditClient audit) {
        this.repository = repository;
        this.audit = audit;
    }

    @PostMapping
    @PreAuthorize("hasAnyRole('ADMIN','ANALYST')")
    @Transactional
    public ResponseEntity<CustomerResponse> create(@Valid @RequestBody CustomerRequest request, Authentication auth) {
        if (repository.existsByEmailIgnoreCase(request.email())) {
            throw ApiException.conflict("A customer with this email already exists");
        }
        Customer saved = repository.save(new Customer(request.firstName(), request.lastName(),
                request.email().toLowerCase(), request.country(), request.segment()));
        audit(auth, "CUSTOMER_CREATED", saved.getId());
        return ResponseEntity.status(HttpStatus.CREATED).body(CustomerResponse.of(saved));
    }

    @GetMapping
    @PreAuthorize("hasAnyRole('ADMIN','ANALYST')")
    public PageResponse<CustomerResponse> list(@RequestParam(defaultValue = "0") int page,
                                               @RequestParam(defaultValue = "20") int size) {
        PageRequest pageable = PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), 100),
                Sort.by("createdAt").descending());
        return PageResponse.of(repository.findAll(pageable), CustomerResponse::of);
    }

    /** The caller's own customer record (CUSTOMER role). */
    @GetMapping("/me")
    @PreAuthorize("hasRole('CUSTOMER')")
    public CustomerResponse me(Authentication auth) {
        UUID customerId = AuthenticatedUser.from(auth).customerId();
        return get(customerId, auth);
    }

    @GetMapping("/{id}")
    public CustomerResponse get(@PathVariable UUID id, Authentication auth) {
        requireAccess(auth, id);
        return repository.findById(id).map(CustomerResponse::of).orElseThrow(() -> ApiException.notFound("Customer"));
    }

    @PutMapping("/{id}")
    @Transactional
    public CustomerResponse update(@PathVariable UUID id, @Valid @RequestBody CustomerUpdate request, Authentication auth) {
        requireAccess(auth, id);
        Customer customer = repository.findById(id).orElseThrow(() -> ApiException.notFound("Customer"));
        customer.update(request.firstName(), request.lastName(), request.country());
        audit(auth, "CUSTOMER_UPDATED", id);
        return CustomerResponse.of(customer);
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    @Transactional
    public ResponseEntity<Void> delete(@PathVariable UUID id, Authentication auth) {
        if (!repository.existsById(id)) {
            throw ApiException.notFound("Customer");
        }
        repository.deleteById(id);
        audit(auth, "CUSTOMER_DELETED", id);
        return ResponseEntity.noContent().build();
    }

    private static void requireAccess(Authentication auth, UUID customerId) {
        if (!AuthenticatedUser.from(auth).canAccessCustomer(customerId)) {
            throw ApiException.forbidden();
        }
    }

    private void audit(Authentication auth, String action, UUID customerId) {
        AuthenticatedUser user = AuthenticatedUser.from(auth);
        audit.record(AuditEvent.of(String.valueOf(user.username()), user.role(), action, "Customer", customerId.toString()));
    }
}
