package com.riskpulse.common.web;

import jakarta.validation.ConstraintViolationException;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/**
 * RFC 7807 error mapping. Responses never contain stack traces, SQL, class names or the rejected values
 * (OWASP API8 / A05); unexpected errors are logged server-side with a correlation id returned to the caller.
 */
@RestControllerAdvice
public class ApiExceptionHandler {

    private static final Logger LOG = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(ApiException.class)
    ResponseEntity<ProblemDetail> handleApi(ApiException e) {
        return problem(e.status(), e.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> handleValidation(MethodArgumentNotValidException e) {
        List<String> errors = e.getBindingResult().getFieldErrors().stream()
                .map(f -> f.getField() + ": " + f.getDefaultMessage())
                .toList();
        ResponseEntity<ProblemDetail> response = problem(HttpStatus.BAD_REQUEST, "Validation failed");
        response.getBody().setProperty("errors", errors);
        return response;
    }

    @ExceptionHandler(ConstraintViolationException.class)
    ResponseEntity<ProblemDetail> handleConstraint(ConstraintViolationException e) {
        List<String> errors = e.getConstraintViolations().stream()
                .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                .toList();
        ResponseEntity<ProblemDetail> response = problem(HttpStatus.BAD_REQUEST, "Validation failed");
        response.getBody().setProperty("errors", errors);
        return response;
    }

    @ExceptionHandler({HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class,
        MissingServletRequestParameterException.class})
    ResponseEntity<ProblemDetail> handleMalformed(Exception e) {
        return problem(HttpStatus.BAD_REQUEST, "Malformed request");
    }

    @ExceptionHandler(AccessDeniedException.class)
    ResponseEntity<ProblemDetail> handleDenied(AccessDeniedException e) {
        return problem(HttpStatus.FORBIDDEN, "Access denied");
    }

    @ExceptionHandler(NoResourceFoundException.class)
    ResponseEntity<ProblemDetail> handleNoResource(NoResourceFoundException e) {
        return problem(HttpStatus.NOT_FOUND, "Resource not found");
    }

    @ExceptionHandler(ResponseStatusException.class)
    ResponseEntity<ProblemDetail> handleStatus(ResponseStatusException e) {
        HttpStatus status = HttpStatus.resolve(e.getStatusCode().value());
        return problem(status == null ? HttpStatus.INTERNAL_SERVER_ERROR : status, e.getReason() == null ? status.getReasonPhrase() : e.getReason());
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ProblemDetail> handleUnexpected(Exception e) {
        String correlationId = UUID.randomUUID().toString();
        LOG.error("Unhandled error, correlationId={}", correlationId, e);
        ResponseEntity<ProblemDetail> response = problem(HttpStatus.INTERNAL_SERVER_ERROR, "Internal server error");
        response.getBody().setProperty("correlationId", correlationId);
        return response;
    }

    private static ResponseEntity<ProblemDetail> problem(HttpStatus status, String detail) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(status, detail);
        body.setTitle(status.getReasonPhrase());
        return ResponseEntity.status(status).contentType(org.springframework.http.MediaType.APPLICATION_PROBLEM_JSON).body(body);
    }
}
