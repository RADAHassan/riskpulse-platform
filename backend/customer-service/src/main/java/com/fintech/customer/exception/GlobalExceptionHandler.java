package com.fintech.customer.exception;

import com.fintech.customer.exception.ErrorResponse.FieldViolation;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.slf4j.MDC;
import org.springframework.core.NestedExceptionUtils;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.time.Instant;
import java.util.List;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(BusinessRuleException.class)
    ResponseEntity<ErrorResponse> handleBusiness(BusinessRuleException ex, HttpServletRequest req) {
        ErrorCode code = ex.getCode();
        return build(code.getHttpStatus(), code.name(), ex.getMessage(), req, null);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException ex, HttpServletRequest req) {
        List<FieldViolation> details = ex.getBindingResult().getFieldErrors().stream()
                .map(e -> new FieldViolation(e.getField(), e.getDefaultMessage()))
                .toList();
        return build(400, ErrorCode.VALIDATION_ERROR.name(), "Request validation failed", req, details);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ErrorResponse> handleUnreadable(HttpMessageNotReadableException ex, HttpServletRequest req) {
        return build(400, ErrorCode.VALIDATION_ERROR.name(), "Malformed or unreadable request body", req, null);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<ErrorResponse> handleTypeMismatch(MethodArgumentTypeMismatchException ex, HttpServletRequest req) {
        return build(400, ErrorCode.VALIDATION_ERROR.name(),
                "Invalid value for parameter '" + ex.getName() + "'", req, null);
    }

    @ExceptionHandler(ObjectOptimisticLockingFailureException.class)
    ResponseEntity<ErrorResponse> handleOptimisticLock(ObjectOptimisticLockingFailureException ex,
                                                       HttpServletRequest req) {
        return build(409, ErrorCode.CONFLICT.name(), "Concurrent modification, please retry", req, null);
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    ResponseEntity<ErrorResponse> handleIntegrity(DataIntegrityViolationException ex, HttpServletRequest req) {
        String cause = String.valueOf(NestedExceptionUtils.getMostSpecificCause(ex).getMessage());
        if (cause.contains("uk_customers_email")) {
            return build(409, ErrorCode.EMAIL_ALREADY_USED.name(), "Email already used", req, null);
        }
        if (cause.contains("customers_pkey")) {
            return build(409, ErrorCode.PROFILE_ALREADY_EXISTS.name(), "Customer profile already exists", req, null);
        }
        log.warn("Data integrity violation: {}", cause);
        return build(409, ErrorCode.CONFLICT.name(), "Conflict with the current state of the data", req, null);
    }

    @ExceptionHandler(ServletException.class)
    ResponseEntity<ErrorResponse> handleServlet(ServletException ex, HttpServletRequest req) {
        int status = (ex instanceof org.springframework.web.ErrorResponse er)
                ? er.getStatusCode().value() : 500;
        String code = status == 404 ? ErrorCode.NOT_FOUND.name()
                : status >= 500 ? ErrorCode.INTERNAL_ERROR.name()
                : ErrorCode.VALIDATION_ERROR.name();
        return build(status, code, status == 404 ? "Resource not found" : "Request cannot be processed", req, null);
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ErrorResponse> handleUnexpected(Exception ex, HttpServletRequest req) {
        log.error("Unexpected error on {}", req.getRequestURI(), ex);
        return build(500, ErrorCode.INTERNAL_ERROR.name(), "Unexpected error", req, null);
    }

    private ResponseEntity<ErrorResponse> build(int status, String code, String message,
                                                HttpServletRequest req, List<FieldViolation> details) {
        ErrorResponse body = new ErrorResponse(Instant.now(), status,
                HttpStatus.valueOf(status).getReasonPhrase(), code, message,
                req.getRequestURI(), MDC.get("correlationId"), details);
        return ResponseEntity.status(status).body(body);
    }
}