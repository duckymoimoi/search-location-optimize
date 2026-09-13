# Local Docker demo runtime

Runtime chính gồm OpenSearch 3.8.0 và FastAPI/model Stage 1. OpenSearch được build
từ tarball chính thức đã kiểm SHA-512; API dùng Python dependency được pin version.
Cả hai cổng 9200 và 8000 chỉ bind vào `127.0.0.1`. Security của OpenSearch bị tắt
cho demo một máy, vì vậy không được expose cổng 9200 ra mạng.

Docker là runtime mặc định của demo:

```powershell
.\bootstrap_docker.ps1  # lần đầu
.\start_docker.ps1
.\stop_docker.ps1
```

`bootstrap_docker.ps1` build hai image local `hanoi-poi/opensearch:3.8.0-local`
và `hanoi-poi/stage1-api:0.1.0-local`. Image OpenSearch được build từ tarball
OpenSearch 3.8.0 chính thức trên Ubuntu 24.04 minimal rootfs đã kiểm checksum.
Thiết lập này tránh phụ thuộc registry khi Docker CDN bị reset. Compose chỉ bind loopback, dùng volume
`hanoi-poi-opensearch-data`, heap 512 MiB và không chạy Dashboards. Checkpoint và
code API được mount read-only vào container API, do đó rebuild image không copy
artifact model. Bản Windows native là fallback khi Docker Desktop không khả dụng:

```powershell
.\start_local.ps1
.\stop_local.ps1
```

Nếu chỉ muốn chạy API trực tiếp trên Windows thay vì container:

```powershell
..\stage1\start_demo_api.ps1
..\stage1\stop_demo_api.ps1
```

`POST /search` yêu cầu `query`, `input_state` (`typing` hoặc `submitted`),
`mode` (`auto`, `lexical`, `dense`, `hybrid`) và `k` từ 1 đến 50.

Ví dụ:

```powershell
$body = @{
  query = "vincom ba trieu"
  input_state = "typing"
  mode = "auto"
  k = 5
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/search `
  -ContentType "application/json; charset=utf-8" -Body $body
```

The runtime archive and extracted distribution are generated dependencies. The
benchmark scripts, frozen mappings and reports live outside `runtime/`.
