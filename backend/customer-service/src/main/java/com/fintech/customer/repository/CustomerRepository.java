package com.fintech.customer.repository;

import com.fintech.customer.domain.Customer;
import com.fintech.customer.domain.CustomerStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;
import java.util.UUID;

@Repository
public interface CustomerRepository extends JpaRepository<Customer, UUID> {

    boolean existsByEmail(String email);

    Optional<Customer> findByEmail(String email);

    Page<Customer> findByStatus(CustomerStatus status, Pageable pageable);

    /** Charge le client ET ses comptes en une seule requete (jointure). */
    @EntityGraph(attributePaths = "accounts")
    Optional<Customer> findWithAccountsByUserId(UUID userId);
}