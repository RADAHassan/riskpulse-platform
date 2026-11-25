package com.fintech.customer.controller;

import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

import java.util.Set;

final class PageRequests {

    static final int MAX_SIZE = 100;

    private PageRequests() {
    }

    static Pageable of(int page, int size, String sort, Set<String> allowedFields,
                       String defaultField, Sort.Direction defaultDirection) {
        if (page < 0) {
            throw invalid("page must be >= 0");
        }
        if (size < 1 || size > MAX_SIZE) {
            throw invalid("size must be between 1 and " + MAX_SIZE);
        }
        Sort order = Sort.by(defaultDirection, defaultField);
        if (sort != null && !sort.isBlank()) {
            String[] parts = sort.split(",");
            String field = parts[0].strip();
            if (!allowedFields.contains(field)) {
                throw invalid("unsupported sort field: " + field);
            }
            Sort.Direction direction = Sort.Direction.ASC;
            if (parts.length > 1) {
                direction = switch (parts[1].strip().toLowerCase()) {
                    case "asc" -> Sort.Direction.ASC;
                    case "desc" -> Sort.Direction.DESC;
                    default -> throw invalid("sort direction must be asc or desc");
                };
            }
            order = Sort.by(direction, field);
        }
        return PageRequest.of(page, size, order);
    }

    private static BusinessRuleException invalid(String message) {
        return new BusinessRuleException(ErrorCode.VALIDATION_ERROR, message);
    }
}