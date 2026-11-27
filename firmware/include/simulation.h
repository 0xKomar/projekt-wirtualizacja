#pragma once

#include <cmath>
#include <cstddef>
#include <cstdint>

struct ReadingWindow {
    float average;
    float minimum;
    float maximum;
};

constexpr bool startsWith(const char* value, const char* prefix) {
    return value != nullptr && prefix != nullptr &&
           (*prefix == '\0' ||
            (*value == *prefix && startsWith(value + 1, prefix + 1)));
}

constexpr bool isPrivateHttpUrl(const char* url) {
    if (!startsWith(url, "http://")) {
        return false;
    }

    const char* cursor = url + 7;
    int octets[4]{};
    for (std::size_t index = 0; index < 4; ++index) {
        const char firstDigit = *cursor;
        unsigned int value = 0;
        std::size_t digitCount = 0;
        while (*cursor >= '0' && *cursor <= '9') {
            if (digitCount == 3) {
                return false;
            }
            value = value * 10U + static_cast<unsigned int>(*cursor - '0');
            if (value > 255U) {
                return false;
            }
            ++cursor;
            ++digitCount;
        }
        if (digitCount == 0 || (digitCount > 1 && firstDigit == '0')) {
            return false;
        }
        octets[index] = static_cast<int>(value);
        if (index < 3) {
            if (*cursor != '.') {
                return false;
            }
            ++cursor;
        }
    }

    if (*cursor != '\0' && *cursor != ':' && *cursor != '/') {
        return false;
    }
    return octets[0] == 10 ||
           (octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31) ||
           (octets[0] == 192 && octets[1] == 168);
}

constexpr bool backendTransportAllowed(const char* url, bool allowInsecureHttp) {
    return startsWith(url, "https://") ||
           (allowInsecureHttp && isPrivateHttpUrl(url));
}

inline bool shouldDelayAfterSample(std::size_t sampleIndex,
                                   std::size_t sampleCount) {
    return sampleIndex < sampleCount && sampleCount - sampleIndex > 1U;
}

inline float syntheticSample(float baseline, uint32_t randomValue) {
    const int jitterTenths = static_cast<int>(randomValue % 61U) - 30;
    float sample = baseline + static_cast<float>(jitterTenths) / 10.0F;
    if (sample < 0.0F) {
        sample = 0.0F;
    } else if (sample > 150.0F) {
        sample = 150.0F;
    }
    return sample;
}

inline bool aggregateSamples(const float* samples, std::size_t count,
                             ReadingWindow& result) {
    if (samples == nullptr || count == 0) {
        return false;
    }

    double total = 0.0;
    float minimum = 150.0F;
    float maximum = 0.0F;
    for (std::size_t index = 0; index < count; ++index) {
        const float sample = samples[index];
        if (!std::isfinite(sample) || sample < 0.0F || sample > 150.0F) {
            return false;
        }
        total += sample;
        if (sample < minimum) {
            minimum = sample;
        }
        if (sample > maximum) {
            maximum = sample;
        }
    }

    result.average = static_cast<float>(total / count);
    result.minimum = minimum;
    result.maximum = maximum;
    return true;
}
