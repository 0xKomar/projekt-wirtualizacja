#include <cassert>
#include <cmath>
#include <cstdint>

#include "simulation.h"

int main() {
    assert(backendTransportAllowed("https://api.example", false));
    assert(!backendTransportAllowed("http://192.168.1.10:8000", false));
    assert(backendTransportAllowed("http://192.168.1.10:8000", true));
    assert(backendTransportAllowed("http://10.0.0.5/api", true));
    assert(backendTransportAllowed("http://172.31.255.255", true));
    assert(!backendTransportAllowed("http://172.32.0.1", true));
    assert(!backendTransportAllowed("http://130.61.136.125:8090", true));
    assert(!backendTransportAllowed("http://backend.local", true));
    assert(!backendTransportAllowed("http://192.168.1.10.evil", true));
    assert(!backendTransportAllowed("ftp://device.lan", true));
    assert(!backendTransportAllowed("", true));

    assert(shouldDelayAfterSample(0, 10));
    assert(shouldDelayAfterSample(8, 10));
    assert(!shouldDelayAfterSample(9, 10));
    assert(!shouldDelayAfterSample(0, 1));

    const float samples[] = {72.0F, 73.0F, 74.0F, 75.0F, 76.0F,
                             77.0F, 78.0F, 75.0F, 74.0F, 76.0F};
    ReadingWindow reading{};
    assert(aggregateSamples(samples, 10, reading));
    assert(std::fabs(reading.average - 75.0F) < 0.001F);
    assert(reading.minimum == 72.0F);
    assert(reading.maximum == 78.0F);

    for (uint32_t seed = 0; seed < 61; ++seed) {
        const float normal = syntheticSample(55.0F, seed);
        const float loud = syntheticSample(75.0F, seed);
        assert(normal >= 52.0F && normal <= 58.0F);
        assert(loud >= 72.0F && loud <= 78.0F);
    }

    assert(!aggregateSamples(nullptr, 0, reading));
    const float invalid[] = {NAN, 1, 1, 1, 1, 1, 1, 1, 1, 1};
    assert(!aggregateSamples(invalid, 10, reading));
    return 0;
}
