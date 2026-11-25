package com.fintech.customer.security;

import com.fintech.customer.exception.BusinessRuleException;
import com.fintech.customer.exception.ErrorCode;
import org.springframework.core.MethodParameter;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;

import java.util.UUID;

public class CurrentUserArgumentResolver implements HandlerMethodArgumentResolver {

    static final String ID = "X-User-Id";
    static final String ROLE = "X-User-Role";
    static final String EMAIL = "X-User-Email";

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return CurrentUser.class.equals(parameter.getParameterType());
    }

    @Override
    public Object resolveArgument(MethodParameter parameter, ModelAndViewContainer mavContainer,
                                  NativeWebRequest request, WebDataBinderFactory binderFactory) {
        String id = request.getHeader(ID);
        String role = request.getHeader(ROLE);
        String email = request.getHeader(EMAIL);
        if (isBlank(id) || isBlank(role) || isBlank(email)) {
            throw unauthenticated();
        }
        String cleanEmail = email.strip();
        if (!cleanEmail.matches("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")) {
            throw unauthenticated();
        }
        try {
            return new CurrentUser(UUID.fromString(id.strip()), Role.valueOf(role.strip()), cleanEmail);
        } catch (IllegalArgumentException e) {
            throw unauthenticated();
        }
    }

    private static boolean isBlank(String s) {
        return s == null || s.isBlank();
    }

    private static BusinessRuleException unauthenticated() {
        return new BusinessRuleException(ErrorCode.UNAUTHENTICATED, "Missing or invalid identity");
    }
}