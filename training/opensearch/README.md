# OpenSearch local build context

Thư mục này chỉ chứa phần cần để build image OpenSearch 3.8.0 local cho [`apps/poi-search`](../../apps/poi-search/README.md).

```powershell
.\training\opensearch\bootstrap_docker.ps1
.\apps\poi-search\scripts\start.ps1
```

`bootstrap_docker.ps1` kiểm checksum, tạo base image Ubuntu tối giản, build image OpenSearch/API bằng Compose của app và chuẩn hóa ownership cho volume `hanoi-poi-opensearch-data`.

Các tarball trong `runtime/` là dependency sinh/tải lại được và không commit. Dữ liệu index sống trong Docker volume; không lưu node data trong workspace.
