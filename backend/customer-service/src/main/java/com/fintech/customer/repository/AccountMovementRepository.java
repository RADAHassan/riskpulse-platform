package com.fintech.customer.repository;

import com.fintech.customer.domain.AccountMovement;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public interface AccountMovementRepository extends JpaRepository<AccountMovement, UUID> {
}