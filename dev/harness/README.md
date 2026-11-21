# ROI page — visual smoke-test harness

Renders `desktop/plugin.js` in a plain browser with a stub
`@hermes/plugin-sdk` and REAL backend payloads, so UI changes can be
checked without a gateway/desktop round-trip.

## Run

    cd dev/harness
    # 1. fetch React UMD builds once (pinned 18.3.1, local afterwards)
    curl -sfL -o react.umd.js    https://cdn.jsdelivr.net/npm/react@18.3.1/umd/react.production.min.js
    curl -sfL -o react-dom.umd.js https://cdn.jsdelivr.net/npm/react-dom@18.3.1/umd/react-dom.production.min.js

    # 2. generate real payloads (deterministic 1014-session fixture store)
    ROI_SAMPLE_OUT=$PWD/sample python3 gen_sample.py

    # 3. copy the current page + serve
    cp ../../desktop/plugin.js plugin.js
    python3 -m http.server 8877
    # http://localhost:8877/            -> full economics view (LV4 fixture)
    # http://localhost:8877/?onboard=1  -> first-run onboarding state

The UMD files are git-ignored (fetched on demand). `sdk-stub.js`
implements `useQuery` as fire-once plus the area constants; the import
map pins ONE React instance shared by the page and the stub (hooks
require it).
