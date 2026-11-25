package com.fintech.customer.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties({AccountDefaultsProperties.class, InternalProperties.class})
public class PropertiesConfig {
}