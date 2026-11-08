package com.dongchen.campus;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

import com.dongchen.campus.config.ReadOnlyDatabaseRepairListener;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CampusServiceApplication {

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(CampusServiceApplication.class);
        application.addListeners(new ReadOnlyDatabaseRepairListener());
        application.run(args);
    }
}
