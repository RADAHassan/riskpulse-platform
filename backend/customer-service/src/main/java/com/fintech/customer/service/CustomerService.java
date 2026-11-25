package com.fintech.customer.service;

import com.fintech.customer.domain.Customer;
import com.fintech.customer.domain.CustomerStatus;
import com.fintech.customer.dto.CreateCustomerRequest;
import com.fintech.customer.dto.CustomerResponse;
import com.fintech.customer.dto.CustomerStatusRequest;
import com.fintech.customer.dto.PageResponse;
import com.fintech.customer.dto.UpdateContactRequest;
import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import com.fintech.customer.mapper.CustomerMapper;
import com.fintech.customer.repository.CustomerRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true) // par defaut : lecture seule ; les ecritures redeclarent @Transactional
public class CustomerService {

    private final CustomerRepository customerRepository;
    private final CustomerMapper customerMapper;

    /** C-01 : userId et email viennent du jeton (H2), jamais du corps de la requete. */
    @Transactional
    public CustomerResponse create(UUID userId, String email, CreateCustomerRequest request) {
        if (customerRepository.existsById(userId)) {
            throw new BusinessRuleException(ErrorCode.PROFILE_ALREADY_EXISTS, "Customer profile already exists");
        }
        if (customerRepository.existsByEmail(email)) {
            throw new BusinessRuleException(ErrorCode.EMAIL_ALREADY_USED, "Email already used");
        }
        Customer customer = new Customer(userId, request.firstName(), request.lastName(), email,
                request.phone(), request.birthDate(), request.address());
        Customer saved = customerRepository.saveAndFlush(customer);
        log.info("Customer profile created userId={}", userId);
        return customerMapper.toResponse(saved);
    }

    /** C-02 et C-05. */
    public CustomerResponse get(UUID userId) {
        return customerMapper.toResponse(find(userId));
    }

    /** C-04 : liste paginee, filtre facultatif sur le statut. */
    public PageResponse<CustomerResponse> list(CustomerStatus status, Pageable pageable) {
        Page<Customer> page = (status == null)
                ? customerRepository.findAll(pageable)
                : customerRepository.findByStatus(status, pageable);
        return PageResponse.from(page.map(customerMapper::toResponse));
    }

    /** C-03 : seuls telephone et adresse sont modifiables. */
    @Transactional
    public CustomerResponse updateContact(UUID userId, UpdateContactRequest request) {
        Customer customer = find(userId);
        customer.updateContact(request.phone(), request.address());
        return customerMapper.toResponse(customerRepository.saveAndFlush(customer));
    }

    /** C-06 : suspendre, reactiver ou cloturer. L'autorisation (ADMIN) est verifiee a l'etape 6. */
    @Transactional
    public CustomerResponse changeStatus(UUID userId, CustomerStatusRequest request) {
        Customer customer = find(userId);
        switch (request.status()) {
            case SUSPENDED -> customer.suspend();
            case ACTIVE -> customer.reactivate();
            case CLOSED -> customer.close();
        }
        Customer saved = customerRepository.saveAndFlush(customer);
        log.info("Customer status changed userId={} status={}", userId, request.status());
        return customerMapper.toResponse(saved);
    }

    private Customer find(UUID userId) {
        return customerRepository.findById(userId)
                .orElseThrow(() -> new BusinessRuleException(ErrorCode.NOT_FOUND, "Customer not found"));
    }
}