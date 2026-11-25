package com.fintech.customer;

import org.springframework.boot.SpringApplication;
import org.testcontainers.utility.TestcontainersConfiguration;

public class TestCustomerServiceApplication {

    public static void main(String[] args) {
        SpringApplication.from(CustomerServiceApplication::main)
                .with(TestcontainersConfiguration.class)
                .run(args);
    }
}