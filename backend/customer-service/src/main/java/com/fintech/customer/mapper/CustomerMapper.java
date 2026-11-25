package com.fintech.customer.mapper;

import com.fintech.customer.domain.Customer;
import com.fintech.customer.dto.CustomerResponse;
import org.mapstruct.Mapper;
import org.mapstruct.ReportingPolicy;

@Mapper(componentModel = "spring", unmappedTargetPolicy = ReportingPolicy.ERROR)
public interface CustomerMapper {

    CustomerResponse toResponse(Customer customer);
}