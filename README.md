# Lab 11 – wydzielenie środowiska produkcyjnego od testowego

| | test | prod |
| --- | --- | --- |
| Przestrzeń nazw | `test` | `prod` |
| Konfiguracja | `k8s/overlays/test/app.env` (ConfigMap) | `k8s/overlays/prod/app.env` |
| Sekrety | środowisko GitHub `test` | środowisko GitHub `production` |
| Baza | PostgreSQL `taskapi_test` (osobny PVC) | PostgreSQL `taskapi_prod` (osobny PVC) |
| Usługa płatności | `payments-sandbox` (klucze `sk_test_`) | `payments-live` (klucze `sk_live_`) |
| Logi | JSON, `LOG_LEVEL=DEBUG` | JSON, `LOG_LEVEL=WARNING` |
| Monitoring | Prometheus http://localhost:30119 | Prometheus http://localhost:30219 |
| Aplikacja | http://localhost:30111 | http://localhost:30211 |
| Wdraża | konto `test:deployer` | konto `prod:deployer`, po zatwierdzeniu |
