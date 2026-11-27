#include <Arduino.h>
#include <HTTPClient.h>
#include <NetworkClientSecure.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <esp_system.h>
#include <time.h>

#include "simulation.h"

#if !defined(WIFI_SSID) || !defined(WIFI_PASSWORD) || !defined(BACKEND_URL) || \
    !defined(DEVICE_KEY)
#error "Set WIFI_SSID, WIFI_PASSWORD, BACKEND_URL, and DEVICE_KEY in the environment"
#endif

#ifndef ALLOW_INSECURE_HTTP
#define ALLOW_INSECURE_HTTP 0
#endif

static_assert(sizeof(WIFI_SSID) > 1, "WIFI_SSID must not be empty");
static_assert(sizeof(WIFI_PASSWORD) > 1, "WIFI_PASSWORD must not be empty");
static_assert(sizeof(BACKEND_URL) > 1, "BACKEND_URL must not be empty");
static_assert(sizeof(DEVICE_KEY) > 1, "DEVICE_KEY must not be empty");
static_assert(
    backendTransportAllowed(BACKEND_URL, ALLOW_INSECURE_HTTP == 1),
    "Use HTTPS or the explicit -http profile on a trusted local network");

#ifndef SIMULATED_LOUD_WINDOWS
#define SIMULATED_LOUD_WINDOWS 4
#endif

namespace {
constexpr std::size_t kSamplesPerWindow = 10;
constexpr std::size_t kPendingCapacity = 3;
constexpr uint32_t kSampleIntervalMs = 10000;
constexpr uint32_t kWifiRetryMs = 5000;
constexpr uint32_t kPostRetryMs = 3000;
constexpr uint32_t kSampleSpacingMs = 1000;
constexpr float kNormalBaseline = 55.0F;
constexpr float kLoudBaseline = 75.0F;

struct PendingReading {
    char json[192];
};

enum class PostResult { kSent, kRetry, kDrop, kRejectedKey };

PendingReading pending[kPendingCapacity];
std::size_t pendingHead = 0;
std::size_t pendingCount = 0;
uint32_t windowIndex = 0;
uint32_t lastWindowMs = 0;
uint32_t lastWifiRetryMs = 0;
uint32_t lastPostAttemptMs = 0;
bool keyRejected = false;
bool timeConfigured = false;

String readingsUrl() {
    String url(BACKEND_URL);
    while (url.endsWith("/")) {
        url.remove(url.length() - 1);
    }
    url += "/api/readings";
    return url;
}

bool formatTimestamp(char* output, std::size_t outputSize) {
    struct tm timeInfo;
    if (!getLocalTime(&timeInfo, 100)) {
        return false;
    }
    return strftime(output, outputSize, "%Y-%m-%dT%H:%M:%SZ", &timeInfo) > 0;
}

void enqueue(const char* payload) {
    if (pendingCount == kPendingCapacity) {
        pendingHead = (pendingHead + 1) % kPendingCapacity;
        --pendingCount;
        Serial.println("Reading buffer full; dropped oldest queued window.");
    }
    const std::size_t tail = (pendingHead + pendingCount) % kPendingCapacity;
    snprintf(pending[tail].json, sizeof(pending[tail].json), "%s", payload);
    ++pendingCount;
}

void sampleAndQueueWindow() {
    const float baseline = windowIndex < SIMULATED_LOUD_WINDOWS
                               ? kLoudBaseline
                               : kNormalBaseline;
    float samples[kSamplesPerWindow];
    for (std::size_t index = 0; index < kSamplesPerWindow; ++index) {
        samples[index] = syntheticSample(baseline, esp_random());
        if (shouldDelayAfterSample(index, kSamplesPerWindow)) {
            delay(kSampleSpacingMs);
        }
    }

    ReadingWindow reading{};
    if (!aggregateSamples(samples, kSamplesPerWindow, reading)) {
        Serial.println("Generated sample window was invalid; not sending it.");
        ++windowIndex;
        return;
    }

    char payload[192];
    char timestamp[32];
    if (formatTimestamp(timestamp, sizeof(timestamp))) {
        snprintf(payload, sizeof(payload),
                 "{\"measured_at\":\"%s\",\"db_avg\":%.1f,"
                 "\"db_min\":%.1f,\"db_max\":%.1f}",
                 timestamp, reading.average, reading.minimum, reading.maximum);
    } else {
        // The API uses receipt time when measured_at is omitted.
        snprintf(payload, sizeof(payload),
                 "{\"db_avg\":%.1f,\"db_min\":%.1f,\"db_max\":%.1f}",
                 reading.average, reading.minimum, reading.maximum);
    }
    enqueue(payload);
    Serial.printf("Queued synthetic window %lu: avg %.1f, min %.1f, max %.1f\n",
                  static_cast<unsigned long>(windowIndex + 1), reading.average,
                  reading.minimum, reading.maximum);
    ++windowIndex;
}

int postReading(NetworkClient& client, const String& url) {
    HTTPClient http;
    if (!http.begin(client, url)) {
        Serial.println("Could not start HTTP request; keeping reading queued.");
        return -1;
    }
    http.setConnectTimeout(4000);
    http.setTimeout(5000);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Device-Key", DEVICE_KEY);
    const int status = http.POST(String(pending[pendingHead].json));
    http.end();
    return status;
}

PostResult postOldestReading() {
    if (pendingCount == 0 || WiFi.status() != WL_CONNECTED) {
        return PostResult::kRetry;
    }

    const String url = readingsUrl();
    int status;
    if (startsWith(BACKEND_URL, "https://")) {
        NetworkClientSecure client;
        client.useBuiltinCACertBundle();
        status = postReading(client, url);
    } else {
#if ALLOW_INSECURE_HTTP == 1
        WiFiClient client;
        status = postReading(client, url);
#else
        Serial.println("Plain HTTP disabled; select an explicit -http profile only on a trusted LAN.");
        return PostResult::kRetry;
#endif
    }

    if (status == 201) {
        Serial.println("Backend accepted synthetic reading (HTTP 201).");
        return PostResult::kSent;
    }
    if (status == 401) {
        Serial.println("Backend rejected DEVICE_KEY (HTTP 401); stopping sends.");
        return PostResult::kRejectedKey;
    }
    if (status < 0 || status >= 500) {
        Serial.printf("Temporary API/network failure (%d); keeping reading queued.\n",
                      status);
        return PostResult::kRetry;
    }

    // Other 4xx responses will not become valid by retrying the same payload.
    Serial.printf("Backend rejected reading (HTTP %d); dropping that window.\n",
                  status);
    return PostResult::kDrop;
}

void flushOneReading() {
    if (keyRejected || pendingCount == 0 || WiFi.status() != WL_CONNECTED) {
        return;
    }
    const uint32_t now = millis();
    if (now - lastPostAttemptMs < kPostRetryMs) {
        return;
    }
    lastPostAttemptMs = now;

    const PostResult result = postOldestReading();
    if (result == PostResult::kSent || result == PostResult::kDrop) {
        pendingHead = (pendingHead + 1) % kPendingCapacity;
        --pendingCount;
    } else if (result == PostResult::kRejectedKey) {
        keyRejected = true;
    }
}

void maintainWifi() {
    if (WiFi.status() == WL_CONNECTED) {
        if (!timeConfigured) {
            configTime(0, 0, "pool.ntp.org", "time.nist.gov");
            timeConfigured = true;
        }
        return;
    }

    const uint32_t now = millis();
    if (now - lastWifiRetryMs >= kWifiRetryMs) {
        lastWifiRetryMs = now;
        Serial.println("Wi-Fi disconnected; retrying connection.");
        WiFi.reconnect();
    }
}
}  // namespace

void setup() {
    Serial.begin(115200);
    delay(250);
    Serial.println("ESP32 synthetic noise sender (no microphone used).");
    Serial.println("Backend readings endpoint configured.");

    WiFi.setHostname("esp32-noise-sim");
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    lastWifiRetryMs = millis();
    lastWindowMs = millis() - kSampleIntervalMs;
    lastPostAttemptMs = millis() - kPostRetryMs;
}

void loop() {
    maintainWifi();

    if (!keyRejected && millis() - lastWindowMs >= kSampleIntervalMs) {
        lastWindowMs = millis();
        sampleAndQueueWindow();
    }

    flushOneReading();
    delay(20);
}
