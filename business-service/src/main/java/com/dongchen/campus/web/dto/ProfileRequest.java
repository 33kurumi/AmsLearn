package com.dongchen.campus.web.dto;

public record ProfileRequest(String displayName, String email, String phone,
                             String targetSchool, Integer examYear) {
}
